// vidgen/space-scale: astronomical scales in three.js without jitter or z-fighting.
// Part of schu-video-generator (MIT licence); imported by a page as "vidgen/space-scale", beside
// "vidgen/three-finish" (it works through Finish's own render calls) and `ctx.orbits`.
//
//   const space = new SpaceView(ctx, {renderer, scene, camera, mode: "enlarged", enlarge: 50});
//   space.add(earthMesh, {body: "Earth"});          // a mesh of radius 1: drawn at the Earth's radius x 50
//   space.add(shipGroup, {body: "Ship"});           // a body without a radius: the object is in metres
//   space.path("Moon");                             // its orbit's path, a line kept exact every frame
//   function frame(t) { space.update(t, {from: {body: "Earth", offset: [0, -3e7, 1e7]}, to: "Earth"}); renderer.render(scene, camera); }
//   space.note().text                               // "sizes not to scale · bodies enlarged 50×; distances to scale"
//
// Floating origin: every position stays a float64 in the orbit data's frame (metres, the mean ecliptic
// of J2000, z its north pole) until the camera's position has been subtracted, in JavaScript's double
// precision; only then does it become three.js's (y up: data (x, y, z) is three's (x, z, -y)). The camera
// stands at three's origin, so what is near it has small, exact coordinates. Paths are rebuilt the
// same way every frame. Depth: `split` (the default) draws the scene in depth slices, the farthest
// first, each with its own near and far planes (each slice spans at most `ratio`), clearing the depth
// buffer between them; a thing is drawn only in the slices its own depth reaches (a world's shell whose depth is
// held off the far plane never covers a nearer slice); any material works, three-finish's motion blur and bloom
// see one picture, its depth of field reads the nearest slice, or the whole range around its focus with
// `dofFocus`. A sky is `scene.background`, or objects marked `userData.sky = true`, or objects with
// `frustumCulled = false` and a negative `renderOrder` (the sky's, a star's in the sky, the warp's; `userData.sky
// = false` keeps one in the world): drawn first, behind everything. `log` uses
// a renderer made with `logarithmicDepthBuffer: true`; `single` one pass with near and far fitted.
// Scale modes: `true` (sizes and distances true), `enlarged` (every body's radius times `enlarge`,
// distances true), `log` (distances compressed as the flat `orbit` scene's `radial: log`:
// r -> AU * log10(1 + r / r0), r0 a third of the smallest periapsis around the central body).
// Nothing here is random and nothing is kept between frames: the picture is a function of t.
import * as THREE from "three";

export const VERSION = 1;
export const AU = 149597870700;
export const MODES = ["true", "enlarged", "log"];
export const DEPTHS = ["split", "log", "single"];
/** The flat `orbit` scene's words (src/vidgen/scenes/orbit.py, orbit_sky.py): its panel's notes. */
export const NOTES = {sizes: "sizes not to scale", distances: "distances compressed (log)",
  enlarged: "bodies enlarged {factors}; distances to scale", logSizes: "bodies enlarged {factors}"};
/** The log view's r0 as a share of the smallest periapsis around the central body (orbit_sky.LOG_R0_SHARE). */
export const LOG_R0_SHARE = 1 / 3;

const PREFIX = "vidgen/space-scale";
const DEFAULTS = {orbits: undefined, renderer: null, scene: null, camera: null, mode: "true", enlarge: 1, depth: "split", ratio: 1e4, join: 3,
  maxSlices: 8, near: 0.01, dofFocus: null, r0: null};
const ADD_KEYS = ["body", "at", "offset", "size", "spin"];
const VIEW_KEYS = ["from", "to", "up", "quaternion"];
const PATH_KEYS = ["kind", "color", "opacity", "parent"];

// ---------- checks ----------
function distance(a, b) {
  const d = Array.from({length: b.length + 1}, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = d[0]; d[0] = i;
    for (let j = 1; j <= b.length; j++) { const cur = d[j]; d[j] = Math.min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = cur; }
  }
  return d[b.length];
}
const fail = (msg) => new Error(`${PREFIX}: ${msg}`);
function hint(key, known) {
  const best = known.map((k) => [distance(String(key).toLowerCase(), k.toLowerCase()), k]).sort((x, y) => x[0] - y[0])[0];
  return best && best[0] <= Math.max(2, String(key).length / 3) ? ` (did you mean "${best[1]}"?)` : "";
}
function checkKeys(where, object, known) {
  if (object === null || typeof object !== "object" || Array.isArray(object)) throw fail(`${where} must be an object, got ${JSON.stringify(object)}`);
  for (const k of Object.keys(object)) if (!known.includes(k)) throw fail(`${where}: unknown option "${k}"${hint(k, known)}; known: ${known.join(", ")}`);
}
function choice(where, v, list) {
  if (!list.includes(v)) throw fail(`${where} must be one of ${list.map((x) => JSON.stringify(x)).join(", ")}, got ${JSON.stringify(v)}${hint(v, list)}`);
  return v;
}
const isVec = (v) => Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === "number" && Number.isFinite(x));

// ---------- numbers (pure, tested in Node) ----------
export const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const scale = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
export const norm = (a) => Math.hypot(a[0], a[1], a[2]);
/** three.js is y up: the data's (x, y, z) is three's (x, z, -y) (as ctx.orbits.yUp). */
export const yUp = (v) => [v[0], v[2], -v[1]];

/** The log view's r0 (m) from orbit data: a third of the smallest periapsis of the bodies going round the
 * central body (each from its first position and velocity: q = h² / (μ (1 + e))); AU / 10 without any,
 * as the flat `orbit` scene's `log_r0`. */
export function logR0(orbits) {
  if (!orbits) return AU / 10;
  const central = orbits.names[0], qs = [];
  for (const name of orbits.names.slice(1)) {
    const b = orbits.bodies[name], o = b.orbit;
    if (b.parent !== central || !o || !o.mu) continue;
    const s = orbits.series(name), r = [s.position[0], s.position[1], s.position[2]], v = [s.velocity[0], s.velocity[1], s.velocity[2]];
    const h = [r[1] * v[2] - r[2] * v[1], r[2] * v[0] - r[0] * v[2], r[0] * v[1] - r[1] * v[0]];
    qs.push((h[0] * h[0] + h[1] * h[1] + h[2] * h[2]) / (o.mu * (1 + o.e)));
  }
  return qs.length ? LOG_R0_SHARE * Math.min(...qs) : AU / 10;
}

/** A position (m, from the central body) in the log view: the same direction, AU * log10(1 + r / r0) from
 * the centre (the flat scene's D = log10(1 + r / r0), drawn in AU). */
export function compress(p, r0) {
  const r = norm(p);
  if (r === 0) return [0, 0, 0];
  return scale(p, AU * Math.log10(1 + r / r0) / r);
}

/** The distance from the origin to the segment a-b. */
export function segmentDistance(a, b) {
  const d = sub(b, a), l2 = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
  const u = l2 > 0 ? Math.min(1, Math.max(0, -(a[0] * d[0] + a[1] * d[1] + a[2] * d[2]) / l2)) : 0;
  return norm(add(a, scale(d, u)));
}

/** The most points a path line gains near the camera in one frame (see nearCuts). */
export const PATH_SPARE = 96;
/** Where to cut the segment a-b (camera-relative) that passes the camera at distance `d` and is over four
 * times as long: the shares u (0..1, rising) of the point nearest the camera and of points d, 2 d, 4 d, ...
 * to both sides of it, at most `spare`. A straight piece drawn as shorter ones is the same line; a piece
 * far longer than its distance from the camera is not drawn at all by software GL (Step 374's finding). */
export function nearCuts(a, b, d, spare = PATH_SPARE) {
  const s = sub(b, a), L = norm(s);
  if (!(L > 4 * d) || spare <= 0) return [];
  const u0 = Math.min(1, Math.max(0, -(a[0] * s[0] + a[1] * s[1] + a[2] * s[2]) / (L * L))), step = Math.max(d, L * 1e-6) / L, out = [];
  if (u0 > 0 && u0 < 1) out.push(u0);
  for (let j = step; out.length < Math.min(spare, 48) && (u0 - j > 0 || u0 + j < 1); j *= 2) { if (u0 - j > 0) out.push(u0 - j); if (u0 + j < 1 && out.length < Math.min(spare, 48)) out.push(u0 + j); }
  return out.sort((x, y) => x - y);
}

/** Cubic Hermite between two frames' positions p0, p1 and velocities v0, v1, dt simulated seconds apart, at
 * u in [0, 1] (u = 0 gives p0 exactly). Motion blur's sub-frame times fall between frames. */
export function hermite(p0, v0, p1, v1, dt, u) {
  const u2 = u * u, u3 = u2 * u;
  const a = 2 * u3 - 3 * u2 + 1, b = u3 - 2 * u2 + u, c = -2 * u3 + 3 * u2, d = u3 - u2;
  return [0, 1, 2].map((i) => a * p0[i] + b * dt * v0[i] + c * p1[i] + d * dt * v1[i]);
}

/** The enlargement factor of `name` from `enlarge` (a number, or {default, <body>: factor}). */
export function factorOf(enlarge, name) {
  if (typeof enlarge === "number") return enlarge;
  return name in enlarge ? enlarge[name] : (enlarge.default ?? 1);
}
const times = (k) => `${Number(k.toPrecision(3))}×`;
function factorsText(enlarge) {
  if (typeof enlarge === "number") return times(enlarge);
  const others = Object.entries(enlarge).filter(([k]) => k !== "default").map(([k, v]) => `${k} ${times(v)}`);
  const base = enlarge.default ?? 1;
  return others.length ? `${times(base)} (${others.join(", ")})` : times(base);
}

/** The honest note for a scale mode, in the flat `orbit` scene's words: `true` nothing; `enlarged` "sizes not
 * to scale" and the factor; `log` "distances compressed (log)" and "sizes not to scale". `words` replaces
 * the wording (another language: {sizes, distances, enlarged, logSizes}, {factors} where the factor goes).
 * Returns {lines, text}: the lines for a panel, the text joined with " · " for a caption. */
export function scaleNote(mode, {enlarge = 1, words = {}} = {}) {
  choice("mode", mode, MODES);
  checkKeys("words", words, Object.keys(NOTES));
  const w = {...NOTES, ...words}, f = factorsText(enlarge);
  const enlarged = typeof enlarge === "number" ? enlarge !== 1 : Object.values(enlarge).some((v) => v !== 1);
  let lines = [];
  if (mode === "enlarged") lines = [w.sizes, w.enlarged.replace("{factors}", f)];
  if (mode === "log") lines = [w.distances, w.sizes, ...(enlarged ? [w.logSizes.replace("{factors}", f)] : [])];
  return {lines, text: lines.join(" · ")};
}

/** Depth slices for view-depth intervals [[near, far], ...] (camera units, near > 0). Overlapping intervals
 * make one stretch; a stretch spanning more than `ratio` (far / near) is cut into equal ratios; separate
 * stretches are drawn apart (each gets the depth buffer's whole precision) unless together they span at most
 * `join`; past `maxSlices` the neighbours spanning least together are joined. Returns [[near, far], ...]
 * from the farthest to the nearest; the pieces of one stretch overlap by 1e-4 (no seam). */
export function depthSlices(intervals, {ratio = 1e4, join = 3, maxSlices = 8, near = 0.01} = {}) {
  const spans = intervals.map(([a, b]) => [Math.max(a, near), Math.max(b, near * 1.0001)]).filter(([a, b]) => b > a).sort((x, y) => x[0] - y[0]);
  if (!spans.length) return [];
  const stretches = [spans[0].slice()];
  for (const [a, b] of spans.slice(1)) {
    const last = stretches[stretches.length - 1];
    if (a <= last[1]) last[1] = Math.max(last[1], b); else stretches.push([a, b]);
  }
  const joined = [stretches[0]];
  for (const s of stretches.slice(1)) {
    const last = joined[joined.length - 1];
    if (s[1] / last[0] <= join) last[1] = s[1]; else joined.push(s);
  }
  const pieces = [];
  for (const [a, b] of joined) {
    const n = Math.max(1, Math.ceil(Math.log(b / a) / Math.log(ratio) - 1e-9));
    for (let i = 0; i < n; i++) pieces.push([i ? a * (b / a) ** (i / n) / 1.0001 : a, i < n - 1 ? a * (b / a) ** ((i + 1) / n) * 1.0001 : b]);
  }
  while (pieces.length > maxSlices) {
    let best = 0;
    for (let i = 1; i < pieces.length - 1; i++) if (pieces[i + 1][1] / pieces[i][0] < pieces[best + 1][1] / pieces[best][0]) best = i;
    pieces.splice(best, 2, [pieces[best][0], pieces[best + 1][1]]);
  }
  return pieces.reverse();
}

// ---------- the view ----------
/** With `dofFocus`, the depth three-finish reads spans from focus / DOF_SPAN to the farthest thing. */
export const DOF_SPAN = 1e5;
const DEPTH_ZERO_VERT = `void main() {
  vec4 p = vec4(position, 1.0);
#ifdef USE_INSTANCING
  p = instanceMatrix * p;
#endif
  gl_Position = projectionMatrix * modelViewMatrix * p; gl_PointSize = 1.0;
}`;
const sphere = new THREE.Sphere(), tmp = new THREE.Vector3();

export class SpaceView {
  /** `ctx` (its `orbits` unless `orbits` is given); `renderer`, `scene`, `camera` (a PerspectiveCamera) are
   * the page's; `mode`, `enlarge`, `depth` as above; `ratio` the most a depth slice spans (far / near), `join`
   * the most two separate groups of things may span together and share a slice;
   * `maxSlices`; `near` the nearest any slice begins (metres); `dofFocus` three-finish's dof focus (metres,
   * an object, or a function of t giving one): the depth is drawn again for its depth of field; `r0` the log view's r0 (default from the data). */
  constructor(ctx, options = {}) {
    checkKeys("SpaceView options", options, Object.keys(DEFAULTS));
    const o = {...DEFAULTS, ...options};
    this.orbits = o.orbits === undefined ? (ctx && ctx.orbits) || null : o.orbits;
    if (!o.renderer || !o.scene || !o.camera) throw fail("SpaceView needs {renderer, scene, camera}");
    if (!o.camera.isPerspectiveCamera) throw fail("the camera must be a THREE.PerspectiveCamera");
    this.renderer = o.renderer; this.scene = o.scene; this.camera = o.camera;
    this.fps = (ctx && ctx.fps) || (this.orbits && this.orbits.fps) || 30;
    this.mode = choice("mode", o.mode, MODES);
    this.depth = choice("depth", o.depth, DEPTHS);
    const e = o.enlarge;
    if (typeof e === "number") { if (!(e > 0)) throw fail(`enlarge must be a positive number, got ${e}`); }
    else {
      checkKeys("enlarge", e, ["default", ...(this.orbits ? this.orbits.names : Object.keys(e))]);
      for (const [k, v] of Object.entries(e)) if (!(typeof v === "number" && v > 0)) throw fail(`enlarge.${k} must be a positive number, got ${JSON.stringify(v)}`);
    }
    const enlarged = typeof e === "number" ? e !== 1 : Object.values(e).some((v) => v !== 1);
    if (this.mode === "true" && enlarged) throw fail('mode "true" draws every size as it is; to enlarge bodies give mode: "enlarged" (its note says so)');
    if (this.mode === "enlarged" && !enlarged) throw fail('mode "enlarged" needs enlarge: a factor other than 1 (e.g. 50), stated in its note');
    this.enlarge = e;
    if (!(o.ratio >= 10)) throw fail(`ratio must be at least 10, got ${o.ratio}`);
    if (!(o.join >= 1)) throw fail(`join must be at least 1, got ${o.join}`);
    if (!(Number.isInteger(o.maxSlices) && o.maxSlices >= 1)) throw fail(`maxSlices must be a whole number from 1, got ${o.maxSlices}`);
    if (!(o.near > 0)) throw fail(`near must be a positive number of metres, got ${o.near}`);
    this.ratio = o.ratio; this.join = o.join; this.maxSlices = o.maxSlices; this.near = o.near; this.dofFocus = o.dofFocus;
    if (this.dofFocus !== null && this.depth !== "split") throw fail('dofFocus goes with depth "split" (three-finish reads a depth buffer of one near and far)');
    this.r0 = this.mode === "log" ? (o.r0 ?? logR0(this.orbits)) : null;
    if (this.depth === "log" && !this.renderer.capabilities.logarithmicDepthBuffer)
      throw fail('depth "log" needs a renderer made with new THREE.WebGLRenderer({..., logarithmicDepthBuffer: true})');
    this.items = []; this.paths = []; this.eye = [0, 0, 0]; this.t = 0; this.slices = [];
    this._render = this.renderer.render.bind(this.renderer);
    const self = this;
    this.renderer.render = function (scene, camera) {
      return scene === self.scene && camera === self.camera ? self._draw() : self._render(scene, camera);
    };
  }

  /** Put `object` in the world: at a body of the orbit data (`body`), or at `at` ([x, y, z] metres in the
   * data's frame, or a function of t giving it), moved by `offset` (metres of the drawing, the data's axes).
   * `size`: "body" (the object has radius 1 and is drawn at the body's radius times its factor; the default
   * for a body with a radius) or a number of metres per unit of the object (default 1), times the body's
   * factor (`enlarge`; an object at `at` is never enlarged). `spin` turns it with the body's rotation
   * (default: when the data has it); its local +y is then the north pole, +x the prime meridian. */
  add(object, options = {}) {
    checkKeys("add", options, ADD_KEYS);
    const item = {object, body: options.body ?? null, at: options.at ?? null, offset: options.offset ?? [0, 0, 0]};
    if (item.body === null && item.at === null) throw fail("add: give body (a name of the orbit data) or at ([x, y, z] metres, or a function of t)");
    if (item.body !== null) this._series(item.body);
    if (!isVec(item.offset)) throw fail(`add: offset must be [x, y, z] metres, got ${JSON.stringify(item.offset)}`);
    const radius = item.body !== null ? this.orbits.bodies[item.body].radius || 0 : 0;
    item.size = options.size ?? (radius > 0 ? "body" : 1);
    if (item.size === "body" && !(radius > 0)) throw fail(`add: ${item.body ?? "this object"} has no radius in the data; give size: metres per unit`);
    if (item.size !== "body" && !(typeof item.size === "number" && item.size > 0)) throw fail(`add: size must be "body" or a positive number, got ${JSON.stringify(item.size)}`);
    item.spin = options.spin ?? (item.body !== null && !!this.orbits.series(item.body).quaternion);
    item.radius = radius;
    if (object.parent !== this.scene) this.scene.add(object);
    this.items.push(item);
    return object;
  }

  /** A line along `name`'s path over the scene (`kind: "path"`) or its orbit at the start (`"conic"`),
   * around its parent; its points are moved with the parent and rebuilt camera-relative every frame. */
  path(name, options = {}) {
    checkKeys("path", options, PATH_KEYS);
    const kind = choice("path kind", options.kind ?? "path", ["path", "conic"]);
    const s = this._series(name), raw = s[kind];
    if (!raw || !raw.length) throw fail(`path: ${name} has no ${kind} in the orbit data`);
    const parent = options.parent ?? this.orbits.bodies[name].parent ?? null;
    const n = raw.length / 3, geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(raw.length + 3 * PATH_SPARE), 3));
    const material = new THREE.LineBasicMaterial({color: options.color ?? 0x8899aa, transparent: (options.opacity ?? 1) < 1, opacity: options.opacity ?? 1});
    const line = new THREE.Line(geometry, material);
    line.frustumCulled = true;
    this.scene.add(line);
    this.paths.push({line, raw, n, parent});
    return line;
  }

  // the per-frame arrays of a body, with a clear error
  _series(name) {
    if (!this.orbits) throw fail(`no orbit data on this page (give the scene orbit_data:), so no body "${name}"`);
    if (!this.orbits.names.includes(name)) throw fail(`no body "${name}"${hint(name, this.orbits.names)}; bodies: ${this.orbits.names.join(", ")}`);
    return this.orbits.series(name);
  }

  /** A body's position (m, data frame, from the central body) at scene time t: the frame's own numbers on a
   * frame, Hermite between two frames' positions and velocities between them (motion blur's sub-frames). */
  position(name, t = this.t) {
    const s = this._series(name), frames = this.orbits.frames, f = t * this.fps;
    const k = Math.min(Math.max(Math.round(f), 0), frames - 1);
    const at = (i) => [s.position[3 * i], s.position[3 * i + 1], s.position[3 * i + 2]];
    if (Math.abs(f - Math.round(f)) < 1e-6 || f <= 0 || f >= frames - 1) return at(k);
    const i = Math.floor(f), u = f - i, vel = (j) => [s.velocity[3 * j], s.velocity[3 * j + 1], s.velocity[3 * j + 2]];
    const dt = this.orbits.time((i + 1) / this.fps) - this.orbits.time(i / this.fps);
    return hermite(at(i), vel(i), at(i + 1), vel(i + 1), dt, u);
  }

  /** A position of the data's frame as drawn: itself, or compressed in the log view. */
  map(p) { return this.mode === "log" ? compress(p, this.r0) : p.slice(); }

  /** Where `name` is drawn at t (metres of the drawing, data frame, float64). */
  at(name, t = this.t) { return this.map(this.position(name, t)); }

  /** The factor `name` is drawn larger by (1 in mode true). */
  factor(name) { return this.mode === "true" ? 1 : factorOf(this.enlarge, name); }

  /** The radius `name` is drawn with (m). */
  radius(name) { this._series(name); return (this.orbits.bodies[name].radius || 0) * this.factor(name); }

  /** The note for this view's mode (scaleNote's {lines, text}). */
  note(words = {}) { return scaleNote(this.mode, {enlarge: this.enlarge, words}); }

  // a point of a view: a body's name, [x, y, z] of the data (mapped), {body, at, offset}, or a function of t
  _point(spec, t, where) {
    if (typeof spec === "function") spec = spec(t);
    if (typeof spec === "string") return this.at(spec, t);
    if (isVec(spec)) return this.map(spec);
    if (spec && typeof spec === "object") {
      checkKeys(where, spec, ["body", "at", "offset"]);
      const base = spec.body !== undefined ? this.at(spec.body, t) : spec.at !== undefined ? this.map(typeof spec.at === "function" ? spec.at(t) : spec.at) : [0, 0, 0];
      return spec.offset ? add(base, spec.offset) : base;
    }
    throw fail(`${where} must be a body's name, [x, y, z] metres, {body, at, offset} or a function of t, got ${JSON.stringify(spec)}`);
  }

  /** Set everything for scene time t: the camera stands at `from` and looks at `to` with `up` (default the
   * data's north, z), or is turned by `quaternion` ([x, y, z, w] of the data's frame; the camera looks along
   * its own -z as a three.js camera does); every object and path is placed relative to the camera. */
  update(t, view) {
    checkKeys("update view", view, VIEW_KEYS);
    this.t = t;
    const eye = this._point(view.from, t, "view.from");
    this.eye = eye;
    const cam = this.camera;
    cam.position.set(0, 0, 0);
    cam.up.set(...yUp(view.up ?? [0, 0, 1]));
    if (view.quaternion) { const q = view.quaternion; cam.quaternion.set(q[0], q[2], -q[1], q[3]); }
    else {
      const to = sub(this._point(view.to, t, "view.to"), eye);
      if (norm(to) === 0) throw fail("update: view.to is where the camera stands");
      cam.lookAt(...yUp(to));
    }
    cam.updateMatrixWorld();
    for (const it of this.items) {
      let p = it.body !== null ? this.at(it.body, t) : this.map(typeof it.at === "function" ? it.at(t) : it.at);
      p = add(sub(p, eye), it.offset);
      it.object.position.set(...yUp(p));
      const k = it.body !== null ? this.factor(it.body) : 1;
      it.object.scale.setScalar(it.size === "body" ? it.radius * k : it.size * k);
      if (it.spin) {
        const q = this.orbits.quaternion(it.body, t);
        if (q) it.object.quaternion.set(q[0], q[2], -q[1], q[3]);
      }
    }
    for (const p of this.paths) {
      const origin = p.parent ? this.position(p.parent, t) : [0, 0, 0], a = p.line.geometry.attributes.position.array;
      let nearest = Infinity, prev = null, k = 0, spare = PATH_SPARE;
      const put = (w) => { a[3 * k] = w[0]; a[3 * k + 1] = w[2]; a[3 * k + 2] = -w[1]; k++; };
      for (let i = 0; i < p.n; i++) {
        const w = sub(this.map(add(origin, [p.raw[3 * i], p.raw[3 * i + 1], p.raw[3 * i + 2]])), eye);
        if (prev) {
          const d = segmentDistance(prev, w);
          nearest = Math.min(nearest, d);
          for (const u of nearCuts(prev, w, d, spare)) { put(add(prev, scale(sub(w, prev), u))); spare--; }
        } else nearest = norm(w);
        put(w);
        prev = w;
      }
      p.line.userData.nearest = nearest;   // how near the camera the line comes (for the depth slices)
      p.line.geometry.setDrawRange(0, k);
      for (const end = k - 1, total = p.n + PATH_SPARE; k < total; k++) { a[3 * k] = a[3 * end]; a[3 * k + 1] = a[3 * end + 1]; a[3 * k + 2] = a[3 * end + 2]; }   // unused points: on the last one, for the bounds
      p.line.geometry.attributes.position.needsUpdate = true;
      p.line.geometry.computeBoundingSphere();
    }
    return this;
  }

  /** The radius in pixels `name` appears with now (after update): a true-scale body may be smaller than one. */
  pixels(name, height = this.renderer.domElement.height) {
    const d = norm(sub(this.at(name), this.eye)), r = this.radius(name);
    if (d <= r) return Infinity;
    return Math.asin(r / d) / (this.camera.fov * Math.PI / 360) * height / 2;
  }

  /** What would mislead in the picture now (after update): an enlarged body swallowing another's centre. */
  problems() {
    const out = [];
    if (!this.orbits || this.mode === "true") return out;
    const names = this.orbits.names;
    for (const a of names) for (const b of names) {
      if (a === b || !(this.radius(a) > 0)) continue;
      if (norm(sub(this.at(a), this.at(b))) < this.radius(a))
        out.push(`${a}, drawn ${times(this.factor(a))} its size, covers ${b}'s centre: give ${a} a smaller factor (enlarge: {default: ..., ${a}: ...})`);
    }
    return out;
  }

  // what the scene draws now (meshes, lines, points, sprites)
  _drawables() {
    const out = [];
    this.scene.traverseVisible((o) => { if ((o.isMesh || o.isLine || o.isPoints || o.isSprite) && o.geometry) out.push(o); });
    return out;
  }

  // view-depth intervals [near, far] of those of `objects` the camera can see (three's units are metres)
  _intervals(objects) { return this._spans(objects).map((x) => x[1]); }

  // [object, [near, far]] for those of `objects` the camera can see
  _spans(objects) {
    const cam = this.camera, out = [], tanY = Math.tan(cam.fov * Math.PI / 360), tanX = tanY * cam.aspect;
    const cy = 1 / Math.hypot(1, tanY), cx = 1 / Math.hypot(1, tanX);
    for (const o of objects) {
      const g = o.geometry;
      if (o.isSprite) sphere.set(tmp.set(0, 0, 0), 0.7072);
      else if (o.isInstancedMesh || o.isBatchedMesh) { if (o.boundingSphere === null) o.computeBoundingSphere(); sphere.copy(o.boundingSphere); }
      else { if (g.boundingSphere === null) g.computeBoundingSphere(); sphere.copy(g.boundingSphere); }
      sphere.applyMatrix4(o.matrixWorld);
      const c = tmp.copy(sphere.center).applyMatrix4(cam.matrixWorldInverse), r = sphere.radius, z = -c.z;
      if (z + r <= 0) continue;                                                     // behind the camera
      if ((Math.abs(c.x) - z * tanX) * cx > r || (Math.abs(c.y) - z * tanY) * cy > r) continue;   // beside the frame
      // (a line's `nearest` is a distance: at the frame's corner its depth along the view is that times cx * cy at least)
      // outside its bounding sphere but beside the view's axis: no point of it is nearer than (distance - r), so no
      // point in the frame has a smaller depth than that times cx * cy (a world added with `at` and `size`)
      const d = c.length(), outside = d > r ? Math.max(this.near, (d - r) * 0.999 * cx * cy) : this.near, surface = this._surface(o);
      const inside = o.userData.nearest !== undefined ? Math.max(this.near, o.userData.nearest * 0.999 * cx * cy) : surface > this.near ? surface : outside;
      out.push([o, [z - r > this.near ? z - r : inside, z + r]]);                   // inside its bounding sphere: how near it comes
    }
    return out;
  }

  // how near the surface of the round body `object` belongs to is (an object added with size "body", or a
  // child of one), else the view's `near`
  _surface(object) {
    for (const it of this.items) {
      if (it.size !== "body") continue;
      let o = object;
      while (o && o !== it.object) o = o.parent;
      if (!o) continue;
      const r = it.object.scale.x, d = it.object.position.length();
      return d > r ? Math.max(this.near, (d - r) * 0.5) : this.near;
    }
    return this.near;
  }

  _fit(iv) {
    if (!iv.length) return [this.near, this.near * 1e6];
    return [Math.max(this.near, Math.min(...iv.map((x) => x[0])) * 0.999), Math.max(...iv.map((x) => x[1])) * 1.001];
  }

  _pass(near, far) {
    const cam = this.camera;
    cam.near = near; cam.far = far; cam.updateProjectionMatrix();
    this._render(this.scene, cam);
  }

  // the scene: the sky (objects with frustumCulled = false) first with near and far of its own, then the
  // depth slices from the farthest, the depth buffer cleared before each; background and clearing only on
  // the first pass, shadow maps on the first pass that draws the world (in the sky's pass everything that
  // casts a shadow is hidden)
  _draw() {
    const r = this.renderer, scene = this.scene, cam = this.camera;
    scene.updateMatrixWorld(); cam.updateMatrixWorld();
    const drawn = this._drawables(), all = drawn.filter((o) => !o.userData.overlay);
    if (this.depth !== "split") {
      const [n, f] = this._fit(this._intervals(all));
      this.slices = [[n, f]];
      return this._pass(n, f);
    }
    // overlays (userData.overlay: a lens's glare) are drawn once, over everything, after the last slice
    const isSky = (o) => o.userData.sky === true || (o.userData.sky !== false && !o.frustumCulled && o.renderOrder < 0);
    const sky = all.filter(isSky), world = all.filter((o) => !isSky(o)), overlay = drawn.filter((o) => o.userData.overlay);
    const spans = this._spans(world), iv = spans.map((x) => x[1]);
    const slices = iv.length ? depthSlices(iv, {ratio: this.ratio, join: this.join, maxSlices: this.maxSlices, near: this.near}) : [];
    this.slices = slices;
    const background = scene.background, autoClear = r.autoClear, shadows = r.shadowMap.autoUpdate;
    let hidden = [], passes = 0, shadowed = false;
    const hide = (list) => { for (const o of hidden) o.visible = true; hidden = list; for (const o of list) o.visible = false; };
    const next = (world = false) => {
      r.shadowMap.autoUpdate = shadows && world && !shadowed;
      if (world) shadowed = true;
      if (passes++ === 0) return;
      scene.background = null; r.autoClear = false; r.clearDepth();
    };
    try {
      if (sky.length) { hide([...world, ...overlay]); next(); this._pass(...this._fit(this._intervals(sky))); }
      hide([...sky, ...overlay]);
      // a slice draws what its depth reaches: a thing that begins beyond it is hidden there (else a shell that
      // keeps its depth off the far plane would be drawn over the nearer things' farther parts)
      for (const [n, f] of slices) { next(true); hide([...sky, ...overlay, ...spans.filter(([, [a]]) => a > f * 1.0001).map(([o]) => o)]); this._pass(n, f); }
      if (passes === 0) { next(true); this._pass(this.near, this.near * 1e6); }
      if (overlay.length) { hide([...sky, ...world]); next(); this._render(scene, cam); }
      if (this.dofFocus !== null && slices.length) this._dofDepth(slices);
    } finally {
      hide([]);
      scene.background = background; r.autoClear = autoClear; r.shadowMap.autoUpdate = shadows;
    }
  }

  // three-finish's depth of field reads one depth buffer with the camera's near and far: after the slices,
  // the depth again, of everything from zf / DOF_SPAN to the farthest (a 24-bit buffer then tells depths
  // near the focus apart to a few per cent), and what is nearer at depth 0 (as near as can be: most blur)
  _dofDepth(slices) {
    const r = this.renderer, scene = this.scene, cam = this.camera;
    let focus = typeof this.dofFocus === "function" ? this.dofFocus(this.t) : this.dofFocus;
    if (focus && focus.isObject3D) focus = -focus.getWorldPosition(new THREE.Vector3()).applyMatrix4(cam.matrixWorldInverse).z;
    if (!(focus > 0)) throw fail(`dofFocus must give a distance in metres or an object in front of the camera, got ${focus}`);
    const nearest = slices[slices.length - 1][0], far = slices[0][1], cut = Math.max(nearest, Math.min(focus / DOF_SPAN, far / 10));
    const override = scene.overrideMaterial;
    this._depthOnly ??= new THREE.MeshBasicMaterial({colorWrite: false});
    this._depthZero ??= new THREE.ShaderMaterial({colorWrite: false, vertexShader: DEPTH_ZERO_VERT, fragmentShader: "void main() { gl_FragDepth = 0.0; }"});
    try {
      scene.background = null; r.autoClear = false; r.clearDepth();   // put back by _draw
      if (cut > nearest * 1.0001) {
        cam.near = nearest; cam.far = cut * 1.0001; cam.updateProjectionMatrix();
        scene.overrideMaterial = this._depthZero; this._render(scene, cam);
      }
      cam.near = cut; cam.far = far; cam.updateProjectionMatrix();
      scene.overrideMaterial = this._depthOnly; this._render(scene, cam);
    } finally { scene.overrideMaterial = override; }
  }

  /** Give the renderer its own render back. */
  dispose() { this.renderer.render = this._render; }
}
