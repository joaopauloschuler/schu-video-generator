// vidgen/space-descent: one world from orbit to the ground (DESIGN.md §123.13). Part of
// schu-video-generator (MIT licence); imported by a page as "vidgen/space-descent".
//
//   import {world} from "vidgen/space-descent";
//   const w = world(renderer, {planet: "earth", at: [8, -150], sun: [38, 250], sea: {state: "breeze"}, clouds: {sky: "fair"}, scene});
//   scene.add(w.object);
//   const cam = airCamera({camera, ...w.rig});                       // vidgen/space-camera-air: descend, ascend, skim, ...
//   function frame(t) { cam.apply(t, cam.descend(t, {over: [0, 10], from: 400e3, to: 300})); w.update(t, {camera}); renderer.render(scene, camera); }
//
// What it joins. The globe of vidgen/space-bodies (the world seen whole: its baked map, its cloud layer),
// the air of vidgen/space-air, and under it the sea (vidgen/space-sea), the ground (vidgen/space-land) and
// the cloud decks (vidgen/space-clouds), all for the same planet, the same place on it and the same sun, in
// ONE frame: the scene's local frame (metres; the origin on the world's sphere under the place `at`, +x
// east, +y up, +z south; the world's middle at [0, -radius, 0]). The globe is turned so that `at` is under
// the origin. A camera at any height from the surface to orbit sees one picture:
//
//   - the air is one model at every height (vidgen/space-air's dome: sky from inside, limb from outside);
//     the globe is made WITHOUT its own air and seen through that same air, lit as the dome's ground is
//     (the sun after the air at each place, the sky's light): one source for the air's look, no handover;
//   - the surface is the globe where a pixel's ground is far from the camera and the sea, ground and decks
//     where it is near: the globe's picture is laid over theirs with a weight that grows with the
//     distance to the ground on the pixel's ray and with the camera's height (HANDOVERS; in logarithms, so
//     a descent that spends equal time in each power of ten of height crosses the handover slowly);
//   - above the handover only the globe is drawn (the sea, ground and decks are neither updated nor drawn),
//     below it only they are (the globe is not drawn): `stage`.
//
// What is true and what is not: `World.honest`. Nothing is random at draw time and nothing is kept between
// frames beyond the parts' own tables: the picture is a function of t, the camera and the options.
import * as THREE from "three";
import {air, sunDirection, AIR_GLSL, DISPLAY_GLSL, PSI_TABLE} from "vidgen/space-air";
import {sea} from "vidgen/space-sea";
import {land, placeFrame, PRESETS as LANDS} from "vidgen/space-land";
import {clouds} from "vidgen/space-clouds";
import {planet, resolveOptions} from "vidgen/space-bodies";

export const VERSION = 1;
const PREFIX = "vidgen/space-descent";

/** Where the globe's picture hands over to the sea, ground and decks, in metres. `near`: along a pixel's ray,
 * the distance to the world's sphere from which the globe begins to show and from which it is all there is;
 * `height`: the camera's heights between which that far globe fades out altogether (under height[0] nothing
 * of the globe is drawn). "low": a sea or decks (the decks hold from about 150 km since their cover varies with a
 * broad weather that never repeats; the globe takes the far view and the higher heights). "high": bare ground (vidgen/space-land holds from orbit;
 * the globe is needed only where the ground's own map ends). */
export const HANDOVERS = Object.freeze({
  low: Object.freeze({near: Object.freeze([60e3, 400e3]), height: Object.freeze([2.5e3, 80e3])}),
  high: Object.freeze({near: Object.freeze([150e3, 600e3]), height: Object.freeze([60e3, 300e3])}),
});
/** The stages a camera passes: only the globe; both, cross-faded; only the sea, ground and decks. */
export const STAGES = Object.freeze(["globe", "handover", "local"]);
/** Furthest a camera may stand from the place `at`, as a share of the radius along the ground, before
 * `problems()` says so (the ground's large-scale map ends 0.48 radii from the place). */
export const REACH = 0.3;

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
const span = (where, v) => { if (!Array.isArray(v) || v.length !== 2 || !v.every(isNum) || !(v[0] > 0) || !(v[1] > v[0])) throw fail(`${where} must be [from, to] in metres with 0 < from < to, got ${JSON.stringify(v)}`); return [v[0], v[1]]; };
const smooth = (a, b, x) => { const u = Math.min(1, Math.max(0, (x - a) / (b - a))); return u * u * (3 - 2 * u); };

// ---------- the handover (pure) ----------
/** A handover in full: a name of HANDOVERS or {near: [from, to], height: [from, to]} (metres), checked. */
export function handoverOf(what = "low") {
  if (typeof what === "string") {
    if (!(what in HANDOVERS)) throw fail(`no handover "${what}"${hint(what, Object.keys(HANDOVERS))}; there are: ${Object.keys(HANDOVERS).join(", ")}, or {near: [from, to], height: [from, to]} in metres`);
    return {near: [...HANDOVERS[what].near], height: [...HANDOVERS[what].height]};
  }
  known("handover", what, ["near", "height"]);
  const h = {near: span("handover.near", what.near ?? HANDOVERS.low.near), height: span("handover.height", what.height ?? HANDOVERS.low.height)};
  if (h.height[1] > h.near[1]) throw fail(`handover.height[1] (${h.height[1]} m) must not be over handover.near[1] (${h.near[1]} m): above near[1] every pixel's ground is that far, so the globe must be whole there`);
  return h;
}
/** The globe's share (0..1) of a pixel whose ground is `distance` metres along its ray from a camera `height`
 * metres up; what is left is the sea's, the ground's and the decks'. Smooth and monotonic in both. */
export function globeWeight(height, distance, handover = HANDOVERS.low) {
  const h = Math.max(height, 1e-3), d = Math.max(distance, h, 1e-3);
  return smooth(Math.log(handover.near[0]), Math.log(handover.near[1]), Math.log(d)) * smooth(Math.log(handover.height[0]), Math.log(handover.height[1]), Math.log(h));
}
/** What is drawn for a camera `height` metres up: {name (of STAGES), globe, local (whether each is drawn at
 * all), below (the globe's share straight down), far (its share at the horizon)}. */
export function stageOf(height, handover = HANDOVERS.low) {
  const far = globeWeight(height, Infinity, handover), below = globeWeight(height, height, handover);
  const globe = far > 0, local = below < 1;
  return {name: !local ? "globe" : !globe ? "local" : "handover", globe, local, below, far};
}
/** The distance (metres) from a camera `height` over a sphere of `radius` to the sphere along a ray whose
 * cosine to the vertical is `mu`; the tangent's length when the ray misses. Exact near the nadir (no
 * difference of large numbers). */
export function surfaceDistance(radius, height, mu) {
  const q = height * (2 * radius + height), b = -(radius + height) * mu;
  return b > 0 && b * b >= q ? q / (b + Math.sqrt(b * b - q)) : Math.sqrt(Math.max(q, 0));
}
/** The turn that brings the globe's place `at` ([latitude, longitude], degrees) under the scene's origin: the
 * rows are the place's east, up and south in the globe's own axes (+y north, +x the prime meridian), so a
 * direction d of the globe is [east . d, up . d, south . d] in the scene. Row-major 3 x 3. */
export function globeTurn(at) {
  const f = placeFrame(at);
  return [f.east, f.up, f.south];
}
/** Where the sun is: [elevation, azimuth] in degrees at the place (azimuth from north through east), or a
 * direction [x, y, z] in the scene's axes. Returns a unit [x, y, z]. */
export function sunOf(sun) {
  if (Array.isArray(sun) && sun.length === 2 && sun.every(isNum)) return sunDirection(sun[0], sun[1]);
  const v = Array.isArray(sun) ? sun : sun && isNum(sun.x) ? [sun.x, sun.y, sun.z] : null;
  if (!v || v.length !== 3 || !v.every(isNum) || Math.hypot(...v) === 0) throw fail(`sun must be [elevation, azimuth] in degrees or a direction [x, y, z], got ${JSON.stringify(sun)}`);
  const n = Math.hypot(...v);
  return v.map((x) => x / n);
}

const OPTIONS = Object.freeze({planet: null, at: null, sun: Object.freeze([35, 200]), air: null, sea: false, land: false, clouds: false, globe: null, handover: null, match: 1,
  exposure: "film", ev: 0, quality: "standard", stars: null, scene: null, shadows: true});
/** The options in full (pure; no drawing): the planet and the place from a ground's preset when not stated,
 * the air from the planet's name, the handover from what lies under the air. */
export function resolveWorld(options = {}) {
  known("world options", options, Object.keys(OPTIONS));
  const o = {...OPTIONS, ...options};
  const part = (name, v, byName) => {
    if (v === false || v === null || v === undefined) return null;
    if (v === true) return {};
    if (typeof v === "string") return {[byName]: v};
    if (typeof v !== "object" || Array.isArray(v)) throw fail(`${name} must be false, true, a name or an options object, got ${JSON.stringify(v)}`);
    return {...v};
  };
  o.sea = part("sea", o.sea, "state"); o.land = part("land", o.land, "preset"); o.clouds = part("clouds", o.clouds, "sky");
  const preset = o.land && typeof o.land.preset === "string" ? LANDS[o.land.preset] ?? null : null;
  o.planet = o.planet ?? (o.land && o.land.world) ?? (preset && preset.world) ?? "earth";
  o.at = o.at ?? (o.land && o.land.at) ?? (preset && preset.at) ?? [0, 0];
  if (!Array.isArray(o.at) || o.at.length !== 2 || !o.at.every(isNum) || Math.abs(o.at[0]) > 90) throw fail(`at must be [latitude, longitude] in degrees, got ${JSON.stringify(o.at)}`);
  o.air = o.air ?? (preset && preset.air) ?? (typeof o.planet === "string" ? o.planet : "earth");
  if (o.air === false) throw fail("a joined world needs an air (an airless world has no descent through one: use vidgen/space-land and vidgen/space-bodies as they are)");
  if (o.land) { o.land.world = o.planet; o.land.at = o.at; }
  o.sun = sunOf(o.sun);
  o.handover = handoverOf(o.handover ?? (o.sea || o.clouds ? "low" : "high"));
  if (!isNum(o.match) || o.match <= 0 || o.match > 10) throw fail(`match must be a number over 0 up to 10 (the globe's brightness beside the sea's and the ground's), got ${JSON.stringify(o.match)}`);
  if (o.globe !== null) { if (typeof o.globe !== "object" || Array.isArray(o.globe)) throw fail(`globe must be options for vidgen/space-bodies' planet, got ${JSON.stringify(o.globe)}`); if ("air" in o.globe) throw fail("globe.air: the joined world's globe has no air of its own (the air is the world's `air`)"); }
  return o;
}

// ---------- the globe's picture over the local one ----------
const OVER_VERT = "varying vec2 vN; void main() { vN = position.xy; gl_Position = vec4(position.xy, 0.0, 1.0); }";
const OVER_FRAG = /* glsl */`
${AIR_GLSL}
${DISPLAY_GLSL}
varying vec2 vN;
uniform sampler2D uGlobe, uAmbient;
uniform vec3 uRight, uTop, uAhead;     // the camera's axes, right and top scaled to the frame's edges
uniform vec4 uHand;                    // the handover: log of near[0], log of near[1], the height's weight, metres a scale height
uniform vec4 uView;                    // the viewport: x, y, width, height
uniform float uMatch, uDisplay, uDecks;
void main() {
  vec4 g = texture2D(uGlobe, (gl_FragCoord.xy - uView.xy) / uView.zw);
  vec3 rd = normalize(uAhead + vN.x * uRight + vN.y * uTop), through; float hit;
  float mu = dot(rd, uAirUp), cosv = dot(rd, uAirSun), hc = uAirGeo.y, q = hc * (2.0 * uAirGeo.x + hc), b = -(uAirGeo.x + hc) * mu;
  // decks beyond the globe's horizon stand over its limb as a thin bright line: where the far globe has taken
  // over, the rays that pass under the decks' tops show the air alone (uDecks: the tops' height in scale heights)
  float over = (uAirGeo.x + hc) * sqrt(max(1.0 - mu * mu, 0.0)) - uAirGeo.x;
  float band = uDecks > 0.0 && b > 0.0 ? uHand.z * (1.0 - g.a) * (1.0 - smoothstep(uDecks, 1.5 * uDecks, over)) : 0.0;
  float tg = b > 0.0 ? q / (b + sqrt(max(b * b - q, 0.0))) : sqrt(q);        // to the world's sphere, in scale heights
  float w = g.a * smoothstep(uHand.x, uHand.y, log(max(tg * uHand.w, 1e-3))) * uHand.z;
  if (w + band < 0.002) discard;
  vec3 col = vec3(0.0), sky = vec3(0.0);
  if (w > 0.0) {
    // the globe's surface lit as the air's own ground is: the sun after the air at that place, and the sky's light
    float sunG = airAt(hc, mu, cosv, uAirMap.w, tg).z;
    vec3 ambient = texture2D(uAmbient, vec2(clamp((sunG - (${PSI_TABLE.sunFrom.toFixed(2)})) / ${(1 - PSI_TABLE.sunFrom).toFixed(2)}, 0.01, 0.99), 0.5)).rgb;
    vec3 lit = g.rgb / max(g.a, 1e-4) * uAirLight * uMatch * (exp(-airTau(0.0, sunG)) + ambient / max(sunG, 0.2));
    vec3 light = airLight(mu, cosv, tg, through, hit);
    col = lit * through + light;
  }
  if (band > 0.0) sky = airLight(mu, cosv, -1.0, through, hit);
  float n = dither(gl_FragCoord.xy) + dither(gl_FragCoord.xy * 1.7 + 91.0) - 1.0;
  gl_FragColor = uDisplay < 0.5 ? vec4(max(col, 0.0) * w + max(sky, 0.0) * band, w + band) : vec4((display(col) + n / 255.0) * w + (display(sky) + n / 255.0) * band, w + band);
}`;

const HONEST = Object.freeze([
  "the camera's descent is a camera's: from orbit to the ground in seconds, far faster and steeper than any vehicle (a real re-entry crosses thousands of kilometres in half an hour)",
  "single clouds of the globe's cloud layer and of the cloud decks are not in the same places: the two agree in colour and roughly in cover, and one dissolves into the other through the handover",
  "the globe's map is soft from low orbit (a texel of a 1024 px map is 10 km wide): between about 200 km and the handover the surface has little detail",
  "the globe's craters of 10 to 30 km and its snow cover are not the ground's: they dissolve through the handover",
  "the globe is lit as a matt ground under the air (the sun after the air, the sky's light): its night side shows no city lights in a joined world",
  "the decks cast no shadow on the globe and the globe's clouds none on the sea or the ground",
  "the frame is the scene's local one: up, the sun and the ground's map are right within about a third of a radius of the place; a flight that leaves it (a real re-entry) needs a world of its own at its end",
]);

/** One world from orbit to the ground. */
export class World {
  /** `renderer`: the page's; `options`: `planet` (a world of vidgen/space-bodies: a name or options; default
   * the ground's own, else "earth"), `at` ([latitude, longitude] of the place under the scene's origin),
   * `sun` ([elevation, azimuth] at the place, or a direction), `air` (vidgen/space-air: a name or options;
   * default the planet's), `sea` / `land` / `clouds` (false, true, a name, or the options of
   * vidgen/space-sea, vidgen/space-land (`preset` ...), vidgen/space-clouds (`sky` ...)), `globe` (more
   * options for the planet: `size`, `clouds`, ...), `handover` (a name of HANDOVERS or {near, height}),
   * `match` (the globe's brightness beside the local picture's, 1), `exposure`, `ev`, `quality`, `stars`,
   * `scene` (the air's own: the lights are added to the scene), `shadows` (vidgen/space-air's: true by default, the
   * decks' and the ground's shadows in the air, and the decks' on the ground and the sea; false: none; or {reach,
   * share, steps}). */
  constructor(renderer, options = {}) {
    if (!renderer || !renderer.isWebGLRenderer) throw fail("world(renderer, options): the first argument must be the page's THREE.WebGLRenderer");
    const o = this.options = resolveWorld(options);
    this.renderer = renderer;
    const airWhat = typeof o.air === "string" ? o.air : {...o.air};
    /** The air (vidgen/space-air): the sky, the limb, the exposure, the lights. */
    this.sky = air(renderer, airWhat, {sun: o.sun, ground: false, exposure: o.exposure, ev: o.ev, quality: o.quality, shadows: o.shadows, ...(o.stars ? {stars: o.stars} : {}), ...(o.scene ? {scene: o.scene} : {})});
    this.radius = this.sky.model.radius;
    /** The ground (vidgen/space-land), the decks (vidgen/space-clouds), the sea (vidgen/space-sea): null when not asked for. */
    this.ground = o.land ? land(renderer, this.sky, {quality: o.quality, ...o.land}) : null;
    this.weather = o.clouds ? clouds(renderer, this.sky, {quality: o.quality, ...o.clouds, ...(this.ground ? {behind: this.ground.behind} : {})}) : null;
    // with shadows in the air the decks shade the ground and the sea too, from the same map (Step 403)
    const shade = this.weather ? this.weather.mapShade : null;
    if (shade && this.ground && !o.land.shade) this.ground.shadedBy(shade);
    this.water = o.sea ? sea(renderer, this.sky, {quality: o.quality, ...(shade ? {shade} : {}), ...o.sea, ...(this.ground ? {depth: this.ground.depth} : {})}) : null;
    /** The globe (vidgen/space-bodies), without air, turned so that the place is under the origin. */
    const size = new THREE.Vector2(); renderer.getDrawingBufferSize(size);
    this.body = planet(renderer, o.planet, {size: size.y >= 300 ? 1024 : 512, ...(this.weather || !("clouds" in resolveOptions(o.planet)) ? {} : {clouds: 0}), ...(o.globe ?? {}), tilt: 0, spin: null, air: false, quality: o.quality});
    const rows = globeTurn(o.at), turn = new THREE.Matrix4().set(...rows[0], 0, ...rows[1], 0, ...rows[2], 0, 0, 0, 0, 1);
    this._holder = new THREE.Group(); this._holder.quaternion.setFromRotationMatrix(turn); this._holder.position.set(0, -this.radius, 0); this._holder.scale.setScalar(this.radius);
    this._holder.add(this.body.object);
    this._globe = new THREE.Scene(); this._globe.add(this._holder);
    this._target = new THREE.WebGLRenderTarget(size.x, size.y, {type: THREE.HalfFloatType, format: THREE.RGBAFormat, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, generateMipmaps: false});
    const h = o.handover;
    this.uniforms = {...this.sky.uniforms, uGlobe: {value: this._target.texture}, uAmbient: {value: this.sky.ambientTexture}, uRight: {value: new THREE.Vector3()}, uTop: {value: new THREE.Vector3()}, uAhead: {value: new THREE.Vector3()},
      uHand: {value: new THREE.Vector4(Math.log(h.near[0]), Math.log(h.near[1]), 1, this.sky.model.H)}, uView: {value: new THREE.Vector4(0, 0, size.x, size.y)}, uMatch: {value: o.match}, uDisplay: {value: 1},
      uDecks: {value: this.weather ? Math.max(...this.weather.decks.map((d) => d.top), ...(this.weather.towers ?? []).map((x) => x.top ?? 0)) / this.sky.model.H : 0}};
    this.material = new THREE.ShaderMaterial({uniforms: this.uniforms, vertexShader: OVER_VERT, fragmentShader: OVER_FRAG, depthTest: false, depthWrite: false, toneMapped: false, fog: false, transparent: false,
      blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor, blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor});
    /** The globe's picture laid over the sea, the ground and the decks (after them, before the scene's own things). */
    this.overlay = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.material);
    this.overlay.name = "world globe"; this.overlay.frustumCulled = false; this.overlay.renderOrder = -790;
    const view = new THREE.Vector4();
    this.overlay.onBeforeRender = (r, scene, camera) => {
      const u = this.uniforms, e = camera.matrixWorld.elements, p = camera.projectionMatrix.elements;
      r.getCurrentViewport(view);
      u.uView.value.copy(view); u.uDisplay.value = r.getRenderTarget() === null ? 1 : 0;
      u.uRight.value.set(e[0], e[1], e[2]).multiplyScalar(1 / p[0]); u.uTop.value.set(e[4], e[5], e[6]).multiplyScalar(1 / p[5]); u.uAhead.value.set(-e[8], -e[9], -e[10]);
      this.material.uniformsNeedUpdate = true;
    };
    /** Everything of the world to add to the scene: the air's dome, the ground, the sea, the decks, the globe's picture. */
    this.object = new THREE.Group(); this.object.name = "world";
    this.object.add(this.sky.object);
    for (const p of [this.ground, this.water, this.weather]) if (p) this.object.add(p.object);
    this.object.add(this.overlay);
    /** The direction towards the sun (a THREE.Vector3, the air's own). */
    this.sun = this.sky.sun;
    /** What the last update drew: `height` (the camera's, metres over the sphere), `stage` (of STAGES), `globe` and `local` (whether each was drawn), `below` and `far` (the globe's share straight down and at the horizon), `up` (the vertical at the camera). */
    this.state = {height: 0, stage: "local", globe: false, local: true, below: 0, far: 0, up: [0, 1, 0]};
    this._clear = new THREE.Color();
    this._seen = false;
  }

  /** What a camera rig of vidgen/space-camera-air wants: `airCamera({camera, ...world.rig})`. */
  get rig() { return {sky: this.sky, ...(this.ground ? {ground: this.ground} : {}), ...(this.water ? {water: this.water} : {}), ...(this.weather ? {clouds: this.weather} : {})}; }
  /** The lights for ordinary meshes (the air's: `sun`, `sky`). */
  get light() { return this.sky.light; }
  /** Where the picture is true and where it is not, as sentences. */
  get honest() { return HONEST; }
  _point(what) {
    if (Array.isArray(what)) return what;
    if (what && what.isObject3D) { what.updateMatrixWorld(); const e = what.matrixWorld.elements; return [e[12], e[13], e[14]]; }
    if (what && isNum(what.x)) return [what.x, what.y, what.z];
    throw fail(`a place must be a camera, an object, a Vector3 or [x, y, z], got ${JSON.stringify(what)}`);
  }
  /** Metres over the world's sphere of a camera, an object or a point [x, y, z]. */
  heightOf(what) { const p = this._point(what); return Math.hypot(p[0], p[1] + this.radius, p[2]) - this.radius; }
  /** The local vertical at a camera, an object or a point: a unit [x, y, z]. */
  up(what) { const p = this._point(what), r = Math.hypot(p[0], p[1] + this.radius, p[2]); return [p[0] / r, (p[1] + this.radius) / r, p[2] / r]; }
  /** What would be drawn for a camera `height` metres up (see `stageOf`). */
  stage(height) { return stageOf(height, this.options.handover); }

  /** The world at scene time `t` for the camera the picture is drawn with: the air, then what the camera's
   * height asks for (the ground, the sea, the decks; the globe's picture). Call it after the camera is placed
   * and before the draw. `sun`: a new direction ([elevation, azimuth] or [x, y, z]). */
  update(t = 0, {camera = null, sun = null} = {}) {
    if (!camera || !camera.isCamera) throw fail("update(t, {camera}): the camera the picture is drawn with is needed");
    camera.updateMatrixWorld();
    this.sky.update(t, {camera, ...(sun ? {sun: sunOf(sun)} : {})});
    const height = this.heightOf(camera), s = stageOf(height, this.options.handover);
    for (const p of [this.ground, this.water, this.weather]) if (p) p.object.visible = s.local;
    if (s.local) {
      if (this.ground) this.ground.update(t, {camera});
      if (this.water) this.water.update(t, {camera});
      if (this.weather) this.weather.update(t, {camera});
    }
    this.overlay.visible = s.globe;
    if (s.globe) {
      const r = this.renderer, was = r.getRenderTarget(), alpha = r.getClearAlpha(), auto = r.autoClear;
      r.getClearColor(this._clear);
      this.body.update(0, {sun: [this.sun.x, this.sun.y, this.sun.z]});
      r.setRenderTarget(this._target); r.setClearColor(0x000000, 0); r.autoClear = true;
      r.render(this._globe, camera);
      r.setRenderTarget(was); r.setClearColor(this._clear, alpha); r.autoClear = auto;
      this.uniforms.uHand.value.z = smooth(Math.log(this.options.handover.height[0]), Math.log(this.options.handover.height[1]), Math.log(Math.max(height, 1e-3)));
    }
    Object.assign(this.state, {height, stage: s.name, globe: s.globe, local: s.local, below: s.below, far: s.far, up: this.up(camera)});
    this._seen = true;
    return this;
  }

  /** What a viewer would see wrong for this camera, as sentences (an empty list when nothing): a camera far
   * from the place, under the surface, or a unit that is not metres. */
  problems(camera = null) {
    const out = [];
    if (this.sky.options.unit !== 1) out.push("the air's unit is not 1: a joined world is a scene in metres");
    if (camera) {
      const p = this._point(camera), up = this.up(p), away = Math.acos(Math.min(1, Math.max(-1, up[1]))), h = this.heightOf(p);
      if (away > REACH) out.push(`the camera is ${(away * this.radius / 1000).toFixed(0)} km along the ground from the place the world is anchored at (at: [${this.options.at.join(", ")}]): beyond ${(REACH * this.radius / 1000).toFixed(0)} km the ground's map ends and the scene's +y is far from up; make a world at the place the shot ends`);
      const floor = Math.max(this.ground ? this.ground.heightAt(p[0], p[2]) : -Infinity, this.water ? this.water.heightAt(p[0], p[2], 0) : -Infinity);
      if (h < (floor === -Infinity ? 0 : floor)) out.push(`the camera is ${((floor === -Infinity ? 0 : floor) - h).toFixed(0)} m under the surface`);
    }
    return out;
  }

  /** Free the parts, the globe's picture and its material. */
  dispose() {
    for (const p of [this.ground, this.water, this.weather, this.sky, this.body]) if (p && typeof p.dispose === "function") p.dispose();
    this._target.dispose(); this.material.dispose(); this.overlay.geometry.dispose();
  }
}

/** One world from orbit to the ground: `world(renderer, {planet: "earth", at: [8, -150], sun: [38, 250], sea: true, clouds: "fair"})`. */
export const world = (renderer, options) => new World(renderer, options);
