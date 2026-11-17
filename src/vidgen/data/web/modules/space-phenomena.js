// vidgen/space-phenomena: black holes, wormholes, a jump to warp, asteroids, comets and auroras for a
// space scene (DESIGN.md §122.9). Part of schu-video-generator (MIT licence); imported by a page as
// "vidgen/space-phenomena".
//
//   import {blackHole, wormhole, warp, asteroids, asteroid, comet, aurora} from "vidgen/space-phenomena";
//   const hole = blackHole(renderer, {sky});                  // sky: the spaceSky of vidgen/space-sky it bends
//   hole.object.scale.setScalar(rs); scene.add(hole.object);  // one unit = the horizon's radius
//   const door = wormhole(renderer, {sky, other: spaceSky(renderer, {seed: 11})});   // a ball that shows another sky
//   const jump = warp(renderer, {seconds: 4, fps: ctx.fps}); scene.add(jump.object);
//   const rocks = asteroids(renderer, {seed: 5, light});      // light: the spaceLight of vidgen/space-light
//   const halley = comet(renderer, {space, body: "Halley"});  // or scene.add(comet(renderer).object) and update(t, {sun, velocity})
//   const lights = aurora(earth);                             // earth: a world of vidgen/space-bodies
//   const update = (t) => { hole.update(t); door.passage(camera, p(t)); sky.set({brightness: jump.update(t, {progress: p(t), camera}).sky});
//                           rocks.update(t, {camera}); halley.update(t); lights.update(t); };
//
// What is physics and what is not. The black hole is a non-rotating one seen by a camera at rest: every
// pixel's light path is stepped round the hole (its exact equation, u'' = -u + 1.5 u^2 with u = 1 /
// radius in Schwarzschild radii, in 28 / 44 / 88 steps), so the shadow has its true size (2.6 radii), the
// sky is bent as it would be (an Einstein ring, second images) and the disc's far side stands over and
// under the shadow; the shift of the disc's light (gravity and its orbit's speed) is exact, its use for
// brightness softened; the disc's temperatures, its gas and the thin ring at the shadow's edge are a
// painter's. The wormhole's paths are an Ellis wormhole's with a straight middle of any length. Both
// bend only the sky (not other things in the scene), inside a ball round them (`lens`) at whose edge
// the bending is eased out so the picture joins the sky. The jump to warp is invented. Asteroids are
// rocks from a seed lit by the scene's lights (the far ones points); a belt's rocks go round by Kepler's
// third law. A comet's tails point away from the sun, the dust tail lagging behind the motion; with
// orbit data they grow as 1 / distance^2. Sizes of comets and belts are stated choices, not to scale.
//
// Cost (1280x720, software GL, 2 cores, over a scene with sky and vidgen/three-finish): a black hole
// that fills the frame 0.75 to 0.9 s a frame ("fast" about 0.2 less, "fine" 0.2 to 0.4 more; without a
// disc 0.3), a wormhole 0.45, a jump 0.1, an asteroid field or belt 0.05, one asteroid close up 0.1, a
// comet 0.05 to 0.1, an aurora 0.1 to 0.2. Everything is a pure function of the time given to update().
//
// Light. Values are linear light for a tone-mapped picture (vidgen/three-finish). Drawn straight to the
// canvas each phenomenon applies the curve and the sRGB encoding itself, as the sky does; light that
// adds up (streaks, tails, curtains) is then only roughly what three-finish would give.
import * as THREE from "three";
import {rng} from "vidgen/music-time";
import {blackbody, starColor, starAmplitude} from "vidgen/space-sky";

export const VERSION = 1;
const PREFIX = "vidgen/space-phenomena";
const TAU = Math.PI * 2;

// ---------- checks ----------
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
function number(where, v, lo, hi) {
  if (typeof v !== "number" || !Number.isFinite(v) || v < lo || v > hi) throw fail(`${where} must be a number from ${lo} to ${hi}, got ${JSON.stringify(v)}`);
  return v;
}
function choice(where, v, list) {
  if (!list.includes(v)) throw fail(`${where} must be one of ${list.map((x) => JSON.stringify(x)).join(", ")}, got ${JSON.stringify(v)}${hint(v, list)}`);
  return v;
}
const isVec = (v) => Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === "number" && Number.isFinite(x));
function vector(where, v) {
  if (v && v.isVector3) return [v.x, v.y, v.z];
  if (!isVec(v)) throw fail(`${where} must be [x, y, z] or a THREE.Vector3, got ${JSON.stringify(v)}`);
  return v.slice();
}
/** `options` over `defaults`; an unknown key stops with the closest known one. */
function resolve(what, options, defaults) {
  if (options === null || typeof options !== "object" || Array.isArray(options)) throw fail(`${what}: the options must be an object, got ${JSON.stringify(options)}`);
  const keys = Object.keys(defaults);
  for (const k of Object.keys(options)) if (!keys.includes(k)) throw fail(`${what}: unknown option "${k}"${hint(k, keys)}; known: ${keys.join(", ")}`);
  return {...defaults, ...options};
}
function needRenderer(what, renderer) {
  if (!renderer || !renderer.isWebGLRenderer) throw fail(`${what}: the first argument must be a THREE.WebGLRenderer`);
}
const clamp01 = (x) => Math.min(1, Math.max(0, x));
const mix = (a, b, u) => a + (b - a) * u;
const smooth = (a, b, x) => { const u = clamp01((x - a) / (b - a)); return u * u * (3 - 2 * u); };
const unit = (v) => { const n = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / n, v[1] / n, v[2] / n]; };
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

/** The quality levels every phenomenon takes. */
export const QUALITIES = Object.freeze(["fast", "normal", "fine"]);

// ---------- shared shader pieces ----------
// to the canvas (no render target): the curve and encoding vidgen/three-finish would apply (ACES, sRGB), as the sky does
const TONE = THREE.ShaderChunk.tonemapping_pars_fragment.replace("uniform float toneMappingExposure;", "const float toneMappingExposure = 1.0;");
const DISPLAY = /* glsl */`
${TONE}
uniform float uDisplay;
float ditherAt(vec2 p) { vec3 q = fract(vec3(p.xyx) * 0.1031); q += dot(q, q.yzx + 33.33); return fract((q.x + q.y) * q.z); }
vec3 display(vec3 c) {
  if (uDisplay < 0.5) return c;
  c = clamp(ACESFilmicToneMapping(max(c, 0.0)), 0.0, 1.0);
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}
vec3 finished(vec3 c) {
  float n = ditherAt(gl_FragCoord.xy) + ditherAt(gl_FragCoord.xy * 1.7 + 91.0) - 1.0;
  return uDisplay < 0.5 ? max(c + n * 0.0009 * smoothstep(0.0, 0.004, c.g), 0.0) : display(c) + n / 255.0;
}`;
// a quad that covers a ball of radius uLens round the object (the whole frame when the camera is inside it): the
// camera's place in the object's units, the view ray in world axes and the object's axes go to the fragment shader
const LENS_VERT = /* glsl */`
uniform float uLens;
varying vec3 vDir, vEye, vAxisX, vAxisY;
void main() {
  vec3 c = (modelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
  float s = length(modelMatrix[0].xyz), R = uLens * s, d = length(c);
  vec3 ray;
  if (d < R * 1.02) {
    vec4 clip = projectionMatrix * vec4(c, 1.0);
    ray = vec3(position.x / projectionMatrix[0][0], position.y / projectionMatrix[1][1], -1.0);
    gl_Position = vec4(position.xy, clip.w > 0.0 ? clamp(clip.z / clip.w, -0.9999, 0.9999) : 0.9999, 1.0);
  } else {
    vec3 f = c / d, right = normalize(cross(f, vec3(0.0, 1.0, 0.0))), up = cross(right, f);
    ray = c + (right * position.x + up * position.y) * (R * d / sqrt(d * d - R * R));
    gl_Position = projectionMatrix * vec4(ray, 1.0);
  }
  vDir = transpose(mat3(viewMatrix)) * ray;
  vEye = (cameraPosition - modelMatrix[3].xyz) / s;
  vAxisX = modelMatrix[0].xyz / s; vAxisY = modelMatrix[1].xyz / s;
}`;
function lensQuad(material, lens) {
  const geometry = new THREE.PlaneGeometry(2, 2);
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), lens);
  geometry.boundingBox = new THREE.Box3(new THREE.Vector3(-lens, -lens, -lens), new THREE.Vector3(lens, lens, lens));
  const mesh = new THREE.Mesh(geometry, material);
  mesh.renderOrder = -900;
  return mesh;
}
const LENS_MATERIAL = {transparent: true, depthTest: true, depthWrite: false, toneMapped: false, fog: false, side: THREE.DoubleSide,
  blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor, blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor};
function blackCube() {
  const data = () => new THREE.DataTexture(new Uint8Array([0, 0, 0, 255]), 1, 1);
  const t = new THREE.CubeTexture(Array.from({length: 6}, data)); t.needsUpdate = true;
  return t;
}
/** What a sky option gives a lens: a SpaceSky (its faint light as the cube it draws itself, its stars as points,
 * its turn) or a cube texture (all of it as a picture), or nothing (black). */
function skyOf(where, sky, picture = false) {
  if (!sky) return {texture: blackCube(), own: true, sky: null, on: 0};
  if (sky.isCubeTexture) return {texture: sky, own: false, sky: null, on: 1};
  if (sky.skyMaterial && sky.object && sky.stars) return {texture: picture ? sky.background : sky.target.texture, own: false, sky, on: 1, picture};
  throw fail(`${where} must be a sky of vidgen/space-sky (spaceSky(renderer, ...)) or a cube texture`);
}
// the gain a SpaceSky draws its cube with now, and the world-to-sky turn (its object may be turned)
function skyState(from, turn) {
  if (!from.sky) { turn.identity(); return from.on; }
  from.sky.object.updateWorldMatrix(true, false);
  turn.setFromMatrix4(from.sky.object.matrixWorld).transpose();
  // (its whole picture, `background`, was drawn with the gain it had then)
  return from.picture ? 1 : from.sky.skyMaterial.uniforms.uGain.value;
}
/** Is the drawing going to the canvas (then a phenomenon applies the tone curve itself, as the sky does)? */
const toCanvas = (renderer) => (renderer.getRenderTarget() === null ? 1 : 0);

// ---------- value noise on the CPU (seeded; for maps made once) ----------
function lattice(seed) {
  const random = rng(seed), table = new Float32Array(4096);
  for (let i = 0; i < 4096; i++) table[i] = random();
  return (ix, iy) => table[(Math.imul(ix, 73856093) ^ Math.imul(iy, 19349663)) & 4095];
}
// smooth noise 0..1 at (x, y); x wraps every `px` cells (0: no wrap)
function noise2(at, x, y, px = 0) {
  const x0 = Math.floor(x), y0 = Math.floor(y), fx = x - x0, fy = y - y0, sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
  const w = (i) => (px ? ((i % px) + px) % px : i);
  const a = at(w(x0), y0), b = at(w(x0 + 1), y0), c = at(w(x0), y0 + 1), d = at(w(x0 + 1), y0 + 1);
  return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
}

// ====================================================================================================
// Black hole
// ====================================================================================================
/** The critical impact parameter of a non-rotating hole in Schwarzschild radii (3 sqrt(3) / 2): the shadow's radius. */
export const SHADOW = 1.5 * Math.sqrt(3);
/** Steps of the light path per pixel at each quality. */
export const HOLE_STEPS = Object.freeze({fast: 28, normal: 44, fine: 88});
export const HOLE_DEFAULTS = Object.freeze({sky: null, disc: true, inner: 3, outer: 14, temperature: 5400, tint: null, brightness: 1, doppler: 0.7, opacity: 0.92,
  speed: 0.5, ring: 1, tilt: 0, lens: null, stars: true, seed: 1, quality: "normal", skyGain: 1});
const HOLE_LIVE = ["inner", "outer", "temperature", "tint", "brightness", "doppler", "opacity", "speed", "ring", "tilt", "skyGain"];
const LENS_MAX = 64;

/** The bending of light past a non-rotating black hole: the total turn (radians) of a ray from far away with
 * impact parameter `b` (Schwarzschild radii; Infinity at and under SHADOW, where the light is caught). */
export function deflection(b, steps = 4000) {
  if (!(b > SHADOW)) return Infinity;
  const total = Math.PI + 1.25 * Math.max(-Math.log(Math.max(b / SHADOW - 1, 1e-9)) - 0.4, 2.5 / b) + 0.35, h = total / steps;
  let u = 1e-9, du = 1 / b, acc = 1.5 * u * u - u, phi = 0;
  for (let i = 0; i < steps; i++) {
    const dh = du + 0.5 * h * acc, un = u + h * dh, an = 1.5 * un * un - un, dn = dh + 0.5 * h * an;
    u = un; du = dn; acc = an; phi += h;
    if (u <= 0) break;
  }
  return phi - u / du - Math.PI;
}
/** The shift g of the light of the disc's gas at radius `r` (Schwarzschild radii) for a far camera (gravity and
 * the orbit's speed): over 1 brighter and bluer, under 1 dimmer and redder. `lz`: the ray's angular momentum about the disc's axis. */
export function discShift(r, lz) { return Math.sqrt(Math.max(1 - 1.5 / r, 0)) / (1 - Math.sqrt(0.5 / (r * r * r)) * lz); }
/** A thin disc's temperature at x = r / inner, over its hottest (at x = 1.36). */
export function discTemperature(x) { return x <= 1 ? 0 : Math.pow(x, -0.75) * Math.pow(1 - 1 / Math.sqrt(x), 0.25) / 0.4880; }
/** The radius (Schwarzschild radii) of the lens drawn round a hole seen from `distance`: 2.6 Einstein radii
 * (sqrt(2 distance)), at least `least`, at most 64. Inside it the sky is bent; toward its edge the bending is eased out. */
export function lensRadius(distance, least = 20) { return Math.min(LENS_MAX, Math.max(least, 2.6 * Math.sqrt(2 * Math.max(distance, 1)))); }
const easeOut = (b, lens) => 1 - smooth(0.55 * lens, lens, b);

/** One light path traced back from a camera at `r0` (Schwarzschild radii from the centre) with impact parameter
 * `b`, as the shader steps it (finer): {beta, u}. `beta`: the angle (radians) between the direction the light
 * came from and the direction of the hole, positive on the side of the picture where it is seen, negative
 * when it came round from the other side; NaN when caught. `u` (when `columns`): 1 / radius at `columns`
 * angles round the hole from 0 to 2 pi (0 once it has left, 2 once caught). `lens`: the eased-out lens radius. */
export function lightPath(r0, b, lens = Infinity, columns = 0) {
  const lapse = Math.sqrt(Math.max(1 - 1 / r0, 1e-4)), sps = Math.min(1, (b * lapse) / r0), cps = -Math.sqrt(1 - sps * sps), psi = Math.atan2(sps, cps);
  const sub = 8, n = columns ? (columns - 1) * sub : 384, h = TAU / n, steps = Math.round(n * 1.3), us = columns ? new Float32Array(columns) : null;
  let u = 1 / r0, du = (-u * cps / Math.max(sps, 1e-9)) * lapse, acc = 1.5 * u * u - u, phi = 0, state = 0;
  if (us) us[0] = u;
  for (let i = 1; i <= steps; i++) {
    if (state === 0) {
      const dh = du + 0.5 * h * acc, un = u + h * dh, an = 1.5 * un * un - un, dn = dh + 0.5 * h * an;
      u = un; du = dn; acc = an; phi += h;
      if (u <= 0) state = 1; else if (u >= 1) state = 2;
    }
    if (us && i % sub === 0 && i / sub < columns) us[i / sub] = state === 0 ? u : state === 1 ? 0 : 2;
  }
  if (state !== 1) return {beta: NaN, u: us};
  const out = phi - u / Math.min(du, -1e-12), ease = Number.isFinite(lens) ? easeOut(b, lens) : 1;
  return {beta: Math.PI - (psi + (out - psi) * ease), u: us};
}
/** The tables the star points read for a camera at `r0` and a lens of radius `lens`: `first` (the star's own
 * image: for 256 angles beta from 0 to `betaMax`, the impact parameter and the gain in brightness), `second`
 * (the image on the far side of the hole: for 256 angles from 0 to pi), and `paths` (rows x columns of 1 / radius:
 * where each of `rows` paths is at `columns` angles round the hole; row i has b = SHADOW + (lens - SHADOW) (i / (rows - 1))^3). */
export function lensTables(r0, lens, {rows = 128, columns = 64, size = 256, gainMax = 24} = {}) {
  const lapse = Math.sqrt(Math.max(1 - 1 / r0, 1e-4)), bs = [], betas = [], paths = new Float32Array(rows * columns);
  const top = Math.min(lens, (r0 / lapse) * 0.999);
  for (let i = 0; i < rows; i++) {
    const s = i / (rows - 1), b = SHADOW * 1.0002 + (top - SHADOW * 1.0002) * s * s * s, path = lightPath(r0, b, lens, columns);
    bs.push(b); betas.push(path.beta); paths.set(path.u, i * columns);
  }
  const theta = (b) => Math.asin(Math.min(1, (b * lapse) / r0));
  // b at a given beta by straight lines between the paths (beta rises with b)
  const invert = (beta) => {
    let lo = 0;
    while (lo < rows - 2 && !(betas[lo + 1] >= beta)) lo++;
    const a = betas[lo], c = betas[lo + 1];
    if (!Number.isFinite(a)) return bs[lo + 1];
    return bs[lo] + (bs[lo + 1] - bs[lo]) * clamp01((beta - a) / Math.max(c - a, 1e-12));
  };
  const betaMax = betas[rows - 1], first = new Float32Array(size * 2), second = new Float32Array(size * 2);
  const fill = (out, sign, span) => {
    for (let k = 0; k < size; k++) {
      const beta = (span * (k + 0.5)) / size, d = span / size / 2, b = invert(sign * beta), b1 = invert(sign * (beta - d)), b2 = invert(sign * (beta + d));
      // a point's light grows as the patch of sky it comes from shrinks: sin(theta) dtheta / (sin(beta) dbeta)
      const gain = Math.abs((Math.sin(theta(b)) * (theta(b2) - theta(b1))) / (Math.sin(beta) * 2 * d));
      out[k * 2] = b; out[k * 2 + 1] = Math.min(gainMax, gain);
    }
  };
  fill(first, 1, betaMax); fill(second, -1, Math.PI);
  return {first, second, paths, betaMax, rows, columns, size, top};
}

// the disc's gas as a map (angle round the hole x radius), seeded: R long streaks, G broad clumps along trailing
// spiral arms, B fine bright filaments, A rings
function discMap(seed) {
  const W = 1024, H = 512, data = new Uint8Array(W * H * 4), a = lattice(seed), b = lattice(seed + 101), c = lattice(seed + 202), e = lattice(seed + 303);
  const rings = new Float32Array(H);
  for (let j = 0; j < H; j++) { const v = j / H; rings[j] = 0.5 * noise2(c, v * 9, 1.5) + 0.3 * noise2(c, v * 23, 7.5) + 0.2 * noise2(c, v * 61, 3.5); }
  for (let j = 0; j < H; j++) {
    const v = j / H;
    for (let i = 0; i < W; i++) {
      const x = i / W, warp = noise2(b, x * 6, v * 3 + 9, 6) - 0.5, xs = x + 0.55 * v;
      const streak = 0.62 * noise2(a, x * 4, v * 8 + warp, 4) + 0.38 * noise2(a, x * 8 + 17.3, v * 17 + 5.1 + warp, 8);
      const clump = 0.6 * noise2(b, xs * 3 + 0.5, v * 2.5 + warp, 3) + 0.4 * noise2(b, xs * 9, v * 6 + 3 + warp, 9);
      let fine = 0, amp = 0.5, fx = 12, fy = 30;
      for (let o = 0; o < 3; o++) { fine += amp * (1 - Math.abs(2 * noise2(e, x * fx + o * 7.7, v * fy + o * 3.3 + 2 * warp, fx) - 1)); amp *= 0.5; fx *= 2; fy *= 2.1; }
      const k = (j * W + i) * 4;
      data[k] = Math.round(255 * clamp01(streak)); data[k + 1] = Math.round(255 * clamp01(clump)); data[k + 2] = Math.round(255 * clamp01(fine / 0.875)); data[k + 3] = Math.round(255 * clamp01(rings[j]));
    }
  }
  const t = new THREE.DataTexture(data, W, H, THREE.RGBAFormat);
  t.wrapS = THREE.RepeatWrapping; t.wrapT = THREE.ClampToEdgeWrapping; t.magFilter = THREE.LinearFilter; t.minFilter = THREE.LinearMipmapLinearFilter; t.generateMipmaps = true; t.needsUpdate = true;
  return t;
}
/** The glow colours of temperatures 1,000 K to 20,000 K (linear, the brightest channel 1; under 1,700 K dimmer) as 64 RGBA texels. */
export function heatRamp() {
  const n = 64, data = new Float32Array(n * 4);
  for (let i = 0; i < n; i++) {
    const T = 1000 + (19000 * i) / (n - 1), c = blackbody(Math.max(T, 1700)), dim = T < 1700 ? Math.pow(T / 1700, 3) : 1, top = Math.max(c[0], c[1], c[2]);
    data.set([(c[0] / top) * dim, (c[1] / top) * dim, (c[2] / top) * dim, 1], i * 4);
  }
  return data;
}
function floatTexture(data, width, height, format = THREE.RGBAFormat) {
  const t = new THREE.DataTexture(data, width, height, format, THREE.FloatType);
  t.magFilter = THREE.NearestFilter; t.minFilter = THREE.NearestFilter; t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping; t.needsUpdate = true;
  return t;
}
function heatTexture() {
  const half = Uint16Array.from(heatRamp(), (v) => THREE.DataUtils.toHalfFloat(v)), t = new THREE.DataTexture(half, 64, 1, THREE.RGBAFormat, THREE.HalfFloatType);
  t.magFilter = THREE.LinearFilter; t.minFilter = THREE.LinearFilter; t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping; t.needsUpdate = true;
  return t;
}

// what the disc lets through and how the lens ends, shared by the picture and the star points
const HOLE_COMMON = /* glsl */`
uniform float uLens;
uniform vec4 uDiscR;      // inner radius, outer radius, on, opacity
const float PI = 3.14159265, BC = 2.59807621;
float lensEdge(float b) { return 1.0 - smoothstep(0.86 * uLens, uLens, b); }
// the share of the disc's width (0 inside to 1 outside) covered at radius r, without the gas's own pattern
float discCover(float v, float clump) {
  float wisp = 1.0 - smoothstep(0.5, 1.0, v + 0.45 * (1.0 - clump) * smoothstep(0.3, 1.0, v));
  return uDiscR.w * smoothstep(0.0, 0.06, v) * wisp;
}`;
const HOLE_FRAG = /* glsl */`
uniform samplerCube uSky; uniform sampler2D uDisc, uHeat; uniform mat3 uSkyTurn;
uniform float uSkyGain, uTime, uRing;
uniform vec4 uDiscLight;  // brightness, doppler, hottest temperature (K), flow (radians a second at the inner edge)
uniform vec3 uTint;
varying vec3 vDir, vEye, vAxisX, vAxisY;
${DISPLAY}
${HOLE_COMMON}
// the light (rgb) and cover (a) of the gas a map sample describes, at a place of temperature base (over the hottest) and width share v
vec4 gasAt(vec4 m, float base, float v) {
  float streak = smoothstep(0.3, 0.7, m.r), clump = smoothstep(0.2, 0.8, m.g), fine = smoothstep(0.45, 0.95, m.b), ring = smoothstep(0.3, 0.7, m.a);
  float gas = (0.3 + 0.7 * streak) * (0.4 + 0.6 * clump) * (0.6 + 0.4 * ring) * (0.5 + 1.1 * fine * fine);
  // one temperature gives colour and light, so dim gas is red and white gas is bright: from white-hot at the hottest
  // ring to a red glow outside (a steeper fall than a thin disc's own temperatures: a stated choice)
  float warm = base * (0.62 + 0.9 * gas);
  vec3 heat = texture2D(uHeat, vec2((uDiscLight.z * warm - 1000.0) / 19000.0 * (63.0 / 64.0) + 0.5 / 64.0, 0.5)).rgb;
  heat = mix(vec3(dot(heat, vec3(0.2126, 0.7152, 0.0722))), heat, 1.2) * uTint;
  float cover = discCover(v, clump) * (0.8 + 0.2 * clamp(gas, 0.0, 1.0));
  return vec4(heat * (uDiscLight.x * 1.25 * warm * warm * sqrt(warm)) * cover, cover);
}
// the disc's light (already times its cover) and cover where the path crosses its plane at 1 / ux radii and angle px along the path
vec4 discAt(float ux, float px, vec3 e1, vec3 e2, vec3 n, vec3 t1, float lz, float lod) {
  float r = 1.0 / max(ux, 1e-4), x = r / uDiscR.x, v = (r - uDiscR.x) / (uDiscR.y - uDiscR.x);
  float on = step(1e-4, ux) * step(0.0, v) * step(v, 1.0);
  v = clamp(v, 0.0, 1.0); x = max(x, 1.0);
  vec3 p = cos(px) * e1 + sin(px) * e2;
  float th = atan(dot(p, cross(n, t1)), dot(p, t1)) / (2.0 * PI);
  float tn = pow(x, -0.75) * pow(max(1.0 - inversesqrt(x), 0.0), 0.25) / 0.4880;
  float g = sqrt(max(1.0 - 1.5 * ux, 0.0)) / max(1.0 - sqrt(0.5 * ux * ux * ux) * lz, 0.05);
  float base = pow(tn, 1.6) * pow(g, uDiscLight.y);
  // the gas turns faster inside: two copies of the map, each sheared for one period, the finished light of one
  // faded out as the other's fades in (so the disc's brightness does not breathe with the period)
  float rate = uDiscLight.w * pow(x, -1.5) / (2.0 * PI), period = 2.4 / max(uDiscLight.w, 1e-3), ph = uTime / period;
  float a1 = fract(ph) - 0.5, a2 = fract(ph + 0.5) - 0.5, w1 = 1.0 - 2.0 * abs(a1);
  vec4 m1 = textureLod(uDisc, vec2(th - rate * (a1 * period) - floor(ph) * 0.37, v), lod);
  vec4 m2 = textureLod(uDisc, vec2(th - rate * (a2 * period) - floor(ph + 0.5) * 0.37 + 0.5, v), lod);
  return mix(gasAt(m2, base, v), gasAt(m1, base, v), w1) * on;
}
void main() {
  vec3 d = normalize(vDir);
  float r0 = length(vEye); vec3 e1 = vEye / r0;
  float cps = dot(d, e1); vec3 q = d - cps * e1; float sps = max(length(q), 1e-5); vec3 e2 = q / sps;
  float u0 = 1.0 / r0, lapse = sqrt(max(1.0 - u0, 1e-4)), b = r0 * sps / lapse, psi = atan(sps, cps);
  // how far round the hole the path goes, about: the steps are shared out over that
  float total = b < BC ? max(psi - 0.5 * PI - acos(min(b, 1.0)), 0.0) - 0.8 * log(max(1.0 - b / BC, 1e-4)) + 0.4
    : psi + 1.25 * max(-log(max(b / BC - 1.0, 1e-4)) - 0.40, 2.5 / b) + 0.35;
  float h = min(total, 2.6 * PI) / float(STEPS), ch = cos(h), sh = sin(h);
  vec3 n = normalize(vAxisY), t1 = normalize(vAxisX);
  float A = dot(e1, n), B = dot(e2, n);
  float u = u0, du = -u0 * cps / sps * lapse, acc = 1.5 * u * u - u, c = 1.0, s = 0.0, phi = 0.0, sd = A, done = 0.0, hits = 0.0;
  vec2 hit1 = vec2(0.0), hit2 = vec2(0.0);
  for (int i = 0; i < STEPS; i++) {
    float dh = du + 0.5 * h * acc, un = u + h * dh, an = 1.5 * un * un - un, dn = dh + 0.5 * h * an;
    float cn = c * ch - s * sh, sn = s * ch + c * sh, sdn = A * cn + B * sn;
    if (done < 0.5) {
#ifdef DISC
      if (sd * sdn < 0.0) {
        float f = sd / (sd - sdn), dl = un - u, f2 = f * f;
        vec2 at = vec2(u + f * h * du + f2 * (3.0 * dl - 2.0 * h * du - h * dn) + f2 * f * (h * du + h * dn - 2.0 * dl), phi + f * h);
        if (hits < 0.5) hit1 = at; else if (hits < 1.5) hit2 = at;
        hits += 1.0;
      }
#endif
      u = un; du = dn; acc = an; c = cn; s = sn; sd = sdn; phi += h;
      if (un <= 0.0 || un >= 1.0) done = 1.0;
    }
  }
  // the bent ray's direction far away; toward the lens's edge the bending is eased out so the picture joins the sky
  float out_ = phi - u / min(du, -1e-6);
  float ease = 1.0 - smoothstep(0.55 * uLens, uLens, b), edge = lensEdge(b);
  float turn = psi + (out_ - psi) * ease;
  vec3 to = cos(turn) * e1 + sin(turn) * e2;
  float fw = max(fwidth(b), 1e-4);
  float open = smoothstep(BC - 0.75 * fw, BC + 0.75 * fw, b);
  vec3 col = vec3(0.0); float through = 1.0;
#ifdef DISC
  float lz = -b * dot(n, cross(e1, e2));
  // the map's level from the pixel's size on the disc (the angle's wrap would upset the built-in choice)
  vec3 p1 = (cos(hit1.y) * e1 + sin(hit1.y) * e2) / max(hit1.x, 1e-3), p2 = (cos(hit2.y) * e1 + sin(hit2.y) * e2) / max(hit2.x, 1e-3);
  float per = 512.0 / (uDiscR.y - uDiscR.x);
  float lod1 = log2(max(max(length(dFdx(p1)), length(dFdy(p1))) * per, 1.0)), lod2 = log2(max(max(length(dFdx(p2)), length(dFdy(p2))) * per, 1.0));
  vec4 d1 = discAt(hit1.x, hit1.y, e1, e2, n, t1, lz, min(lod1, 8.0)) * step(0.5, hits);
  vec4 d2 = discAt(hit2.x, hit2.y, e1, e2, n, t1, lz, min(lod2, 8.0)) * step(1.5, hits);
  col = d1.rgb + (1.0 - d1.a) * d2.rgb;
  through = (1.0 - d1.a) * (1.0 - d2.a);
  // the thin ring of light that went round the hole once more: a line at the shadow's edge, never under a pixel wide
  float sigma = max(0.035, 0.75 * fw), side = 1.0 / max(1.0 - 0.136 * clamp(lz, -5.0, 5.0), 0.3);
  vec3 glow = texture2D(uHeat, vec2((uDiscLight.z * 1.25 * pow(side, uDiscLight.y) - 1000.0) / 19000.0, 0.5)).rgb * uTint;
  col += smoothstep(0.6, 0.97, through) * uRing * uDiscLight.x * glow * 0.7 * pow(side, 3.0 * uDiscLight.y) * (0.035 / sigma) * exp(-0.5 * pow((b - BC * 1.012) / sigma, 2.0));
#endif
  vec3 sky = textureCube(uSky, uSkyTurn * to).rgb * uSkyGain;
  col += through * open * sky;
  gl_FragColor = vec4(finished(col) * edge, edge);
}`;
// a star of the sky as the hole shows it: its own image pushed outward and, with SECOND, the faint one on the far side
const HOLE_STAR_VERT = /* glsl */`
attribute vec3 aDir; attribute vec4 aStar;
uniform sampler2D uImages, uPaths;
uniform mat3 uSkyTurnBack; uniform mat4 uHoleMatrix;
uniform vec4 uCamera;     // the camera's distance (radii), the lapse there, the widest beta, the paths' widest b
uniform vec3 uStarLook;   // sigma (px), gain, glare
varying vec4 vStar; varying float vHalf;
${HOLE_COMMON}
vec2 imageAt(float x, float row) {
  float k = clamp(x, 0.0, 1.0) * 256.0 - 0.5, i = floor(k);
  vec2 a = texelFetch(uImages, ivec2(int(clamp(i, 0.0, 255.0)), int(row)), 0).rg, b = texelFetch(uImages, ivec2(int(clamp(i + 1.0, 0.0, 255.0)), int(row)), 0).rg;
  return mix(a, b, k - i);
}
float pathAt(float row, float angle) {
  float x = clamp(angle / (2.0 * PI), 0.0, 1.0) * float(COLUMNS - 1), y = clamp(row, 0.0, 1.0) * float(ROWS - 1), i = floor(x), j = floor(y);
  ivec2 at = ivec2(int(i), int(j)), far = ivec2(min(int(i) + 1, COLUMNS - 1), min(int(j) + 1, ROWS - 1));
  float a = texelFetch(uPaths, at, 0).r, b = texelFetch(uPaths, ivec2(far.x, at.y), 0).r, c = texelFetch(uPaths, ivec2(at.x, far.y), 0).r, d = texelFetch(uPaths, far, 0).r;
  return mix(mix(a, b, x - i), mix(c, d, x - i), y - j);
}
void main() {
  vec3 centre = uHoleMatrix[3].xyz, toHole = normalize(centre - cameraPosition), dir = normalize(uSkyTurnBack * aDir);
  float cb = dot(dir, toHole), beta = acos(clamp(cb, -1.0, 1.0));
  vec3 side = dir - cb * toHole; side /= max(length(side), 1e-6);
#ifdef SECOND
  vec2 im = imageAt(beta / PI, 1.0); float flip = -1.0, seen = 1.0;
#else
  vec2 im = imageAt(beta / uCamera.z, 0.0); float flip = 1.0, seen = step(beta, uCamera.z);
#endif
  float b = im.x, theta = asin(min(b * uCamera.y / uCamera.x, 1.0));
  vec3 e2 = side * flip, look = cos(theta) * toHole + sin(theta) * e2;
  float through = 1.0;
  if (uDiscR.z > 0.5) {
    // where this path crosses the disc's plane, and what the disc lets through there
    vec3 n = normalize(uHoleMatrix[1].xyz), e1 = -toHole;
    float A = dot(e1, n), B = dot(e2, n), first = atan(-A, B), row = pow(clamp((b - BC * 1.0002) / (uCamera.w - BC * 1.0002), 0.0, 1.0), 1.0 / 3.0);
    first += first < 0.0 ? PI : 0.0;
    for (int k = 0; k < 2; k++) {
      float u = pathAt(row, first + float(k) * PI), v = (1.0 / max(u, 1e-4) - uDiscR.x) / (uDiscR.y - uDiscR.x);
      through *= 1.0 - discCover(clamp(v, 0.0, 1.0), 0.5) * 0.9 * step(1e-4, u) * step(0.0, v) * step(v, 1.0) * step(u, 1.0);
    }
  }
  float A = aStar.a * uStarLook.y * im.y * through * lensEdge(b) * seen;
  float halo = 2.0 * uStarLook.x * sqrt(max(pow(A * uStarLook.z * 0.14 / 0.0015, 2.0 / 3.0) - 1.0, 0.0));
  float size = min(max(3.3 * uStarLook.x, halo), 40.0 * uStarLook.x);
  vStar = vec4(aStar.rgb, A); vHalf = size;
  gl_PointSize = 2.0 * size;
  vec4 clip = projectionMatrix * vec4(mat3(viewMatrix) * look, 1.0), hole = projectionMatrix * viewMatrix * vec4(centre, 1.0);
  clip.z = (hole.w > 0.0 ? clamp(hole.z / hole.w, -0.9999, 0.9999) : 0.9999) * clip.w;
  gl_Position = A > 1e-5 ? clip : vec4(2.0, 2.0, 2.0, 1.0);
}`;
const HOLE_STAR_FRAG = /* glsl */`
varying vec4 vStar; varying float vHalf; uniform vec3 uStarLook;
${DISPLAY}
void main() {
  vec2 p = (gl_PointCoord - 0.5) * 2.0 * vHalf;
  float r2 = dot(p, p), a = 2.0 * uStarLook.x, w = 1.0 + r2 / (a * a);
  float core = exp(-r2 / (2.0 * uStarLook.x * uStarLook.x));
  float halo = uStarLook.z * 0.14 / (w * sqrt(w)) * smoothstep(1.0, 0.6, sqrt(r2) / vHalf);
  gl_FragColor = vec4(display(vStar.rgb * vStar.a * (core + halo)), 1.0);
}`;

/** A non-rotating black hole: `object` (add it to the scene; one unit = the horizon's radius: scale it; its y
 * axis is the disc's axis: turn it), `update(t)`, `set(options)`, `options`, `uniforms`, `lens` (after a draw:
 * the lens's radius), `dispose()`. */
export class BlackHole {
  constructor(renderer, options = {}) {
    needRenderer("blackHole(renderer, options)", renderer);
    const o = this.options = resolve("blackHole", options, HOLE_DEFAULTS);
    choice("blackHole: quality", o.quality, QUALITIES);
    number("blackHole: seed", o.seed, 0, 1e9);
    if (o.lens !== null) number("blackHole: lens", o.lens, 6, LENS_MAX);
    this.renderer = renderer;
    this._sky = skyOf("blackHole: sky", o.sky);
    this.lens = o.lens ?? 20;
    const u = this.uniforms = {uSky: {value: this._sky.texture}, uSkyTurn: {value: new THREE.Matrix3()}, uDisc: {value: o.disc ? discMap(o.seed) : new THREE.DataTexture(new Uint8Array(4), 1, 1)},
      uHeat: {value: heatTexture()}, uSkyGain: {value: 1}, uLens: {value: this.lens}, uTime: {value: 0}, uRing: {value: 1}, uDiscR: {value: new THREE.Vector4()},
      uDiscLight: {value: new THREE.Vector4()}, uTint: {value: new THREE.Vector3(1, 1, 1)}, uDisplay: {value: 0}};
    this.material = new THREE.ShaderMaterial({...LENS_MATERIAL, defines: {STEPS: HOLE_STEPS[o.quality], ...(o.disc ? {DISC: 1} : {})}, uniforms: u, vertexShader: LENS_VERT, fragmentShader: HOLE_FRAG});
    this.object = lensQuad(this.material, LENS_MAX);
    this.object.name = "black hole";
    this._eye = new THREE.Vector3(); this._at = new THREE.Vector3(); this._scale = new THREE.Vector3(); this._key = "";
    this._stars = o.stars && this._sky.sky ? this._starPoints(this._sky.sky) : null;
    this.object.onBeforeRender = (r, scene, camera) => this._before(r, camera);
    this.set({});
    this.update(0);
  }
  // the sky's stars as points of the hole's own, drawn after the picture: each star's own image and its second one
  _starPoints(sky) {
    const s = sky.stars, o = sky.options, dir = new Float32Array(s.count * 3), look = new Float32Array(s.count * 4);
    for (let i = 0; i < s.count; i++) {
      const c = starColor(s.bv[i], 0.7 * o.color);
      dir.set(s.dir.subarray(i * 3, i * 3 + 3), i * 3); look.set([c[0], c[1], c[2], starAmplitude(s.mag[i], o.contrast)], i * 4);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(dir, 3)); geometry.setAttribute("aDir", geometry.getAttribute("position")); geometry.setAttribute("aStar", new THREE.BufferAttribute(look, 4));
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), LENS_MAX);
    const tables = {rows: 128, columns: 64, size: 256};
    const u = this.starUniforms = {uImages: {value: floatTexture(new Float32Array(256 * 2 * 4), 256, 2)}, uPaths: {value: floatTexture(new Float32Array(tables.rows * tables.columns), tables.columns, tables.rows, THREE.RedFormat)},
      uSkyTurnBack: {value: new THREE.Matrix3()}, uHoleMatrix: {value: this.object.matrixWorld}, uCamera: {value: new THREE.Vector4()}, uStarLook: {value: new THREE.Vector3(1, 1, 1)},
      uLens: this.uniforms.uLens, uDiscR: this.uniforms.uDiscR, uDisplay: this.uniforms.uDisplay};
    const made = [];
    for (const second of [false, true]) {
      const material = new THREE.ShaderMaterial({uniforms: u, vertexShader: HOLE_STAR_VERT, fragmentShader: HOLE_STAR_FRAG, defines: {ROWS: tables.rows, COLUMNS: tables.columns, ...(second ? {SECOND: 1} : {})},
        blending: THREE.AdditiveBlending, transparent: true, depthTest: true, depthWrite: false, toneMapped: false, fog: false});
      // (its own list of the stars near enough to the hole to show, written before each draw)
      const chosen = new THREE.BufferGeometry();
      for (const name of ["position", "aDir", "aStar"]) chosen.setAttribute(name, geometry.getAttribute(name));
      chosen.setIndex(new THREE.BufferAttribute(new Uint32Array(s.count), 1).setUsage(THREE.DynamicDrawUsage)); chosen.boundingSphere = geometry.boundingSphere; chosen.setDrawRange(0, 0);
      const points = new THREE.Points(chosen, material);
      points.renderOrder = -899; points.name = second ? "black hole: second images of the stars" : "black hole: stars";
      points.onBeforeRender = () => { material.uniformsNeedUpdate = true; };
      this.object.add(points); made.push(points);
    }
    return {geometry, points: made, tables, sky, dir, reach: [0, Math.PI]};
  }
  // before each draw: the lens for this camera's distance, the sky's gain and turn, the star tables
  _before(renderer, camera) {
    const u = this.uniforms, o = this.options;
    u.uDisplay.value = toCanvas(renderer);
    this.object.matrixWorld.decompose(this._at, new THREE.Quaternion(), this._scale);
    const r0 = Math.max(camera.getWorldPosition(this._eye).distanceTo(this._at) / this._scale.x, 1.02);
    this.lens = o.lens ?? lensRadius(r0, Math.max(20, 1.4 * o.outer));
    u.uLens.value = this.lens;
    u.uSkyGain.value = o.skyGain * skyState(this._sky, u.uSkyTurn.value);
    this.material.uniformsNeedUpdate = true;
    if (!this._stars) return;
    const su = this.starUniforms, sky = this._stars.sky.starUniforms, key = `${r0.toPrecision(7)} ${this.lens.toPrecision(7)}`;
    su.uSkyTurnBack.value.copy(u.uSkyTurn.value).transpose();
    su.uStarLook.value.set(sky.uSigma.value, sky.uGain.value * sky.uThin.value * o.skyGain, sky.uGlare.value);
    if (key !== this._key) {
      this._key = key;
      const t = lensTables(r0, this.lens, this._stars.tables), images = su.uImages.value.image.data;
      for (let k = 0; k < 256; k++) { images.set([t.first[k * 2], t.first[k * 2 + 1], 0, 0], k * 4); images.set([t.second[k * 2], t.second[k * 2 + 1], 0, 0], (256 + k) * 4); }
      su.uPaths.value.image.data.set(t.paths);
      su.uImages.value.needsUpdate = true; su.uPaths.value.needsUpdate = true;
      su.uCamera.value.set(r0, Math.sqrt(Math.max(1 - 1 / r0, 1e-4)), t.betaMax, t.top);
      // how far from the hole's direction a star can stand and still show: inside the lens, and (its second image) while that keeps a 250th of its light
      let last = 0;
      while (last < 255 && t.second[last * 2 + 1] > 0.004) last++;
      this._stars.reach = [t.betaMax, (Math.PI * (last + 2)) / 256];
    }
    // only the stars near enough are drawn (a loop over all of them here is far cheaper than their vertex shader)
    const h = this._eye.clone().sub(this._at).negate().normalize().applyMatrix3(u.uSkyTurn.value), dir = this._stars.dir, n = dir.length / 3;
    this._stars.points.forEach((points, which) => {
      const least = Math.cos(Math.min(Math.PI, this._stars.reach[which] * 1.02)), index = points.geometry.index, list = index.array;
      let count = 0;
      for (let i = 0; i < n; i++) if (dir[i * 3] * h.x + dir[i * 3 + 1] * h.y + dir[i * 3 + 2] * h.z >= least) list[count++] = i;
      index.needsUpdate = true; points.geometry.setDrawRange(0, count);
    });
  }
  /** Change options live: inner, outer, temperature, tint, brightness, doppler, opacity, speed, ring, tilt, skyGain. */
  set(options) {
    for (const k of Object.keys(options)) if (!HOLE_LIVE.includes(k)) throw fail(`blackHole.set: "${k}" cannot change on a made hole${hint(k, HOLE_LIVE)}; live options: ${HOLE_LIVE.join(", ")}`);
    const o = Object.assign(this.options, options), u = this.uniforms, tint = o.tint === null ? [1, 1, 1] : new THREE.Color(o.tint).toArray();
    number("blackHole: inner", o.inner, 1.6, 50); number("blackHole: outer", o.outer, o.inner + 0.5, 60);
    u.uDiscR.value.set(o.inner, o.outer, o.disc ? 1 : 0, number("blackHole: opacity", o.opacity, 0, 1));
    u.uDiscLight.value.set(number("blackHole: brightness", o.brightness, 0, 64), number("blackHole: doppler", o.doppler, 0, 1.5), number("blackHole: temperature", o.temperature, 1000, 20000), number("blackHole: speed", o.speed, 0, 20));
    u.uTint.value.set(...tint); u.uRing.value = number("blackHole: ring", o.ring, 0, 16);
    number("blackHole: skyGain", o.skyGain, 0, 64);
    this.object.rotation.x = THREE.MathUtils.degToRad(number("blackHole: tilt", o.tilt, -180, 180));
    return this;
  }
  /** Set the disc's gas to time t (seconds): a pure function of t. */
  update(t) { this.uniforms.uTime.value = t; return this; }
  dispose() {
    this.object.removeFromParent(); this.object.geometry.dispose(); this.material.dispose();
    this.uniforms.uDisc.value.dispose(); this.uniforms.uHeat.value.dispose();
    if (this._sky.own) this._sky.texture.dispose();
    if (this._stars) { this._stars.geometry.dispose(); for (const p of this._stars.points) { p.material.dispose(); p.geometry.dispose(); } this.starUniforms.uImages.value.dispose(); this.starUniforms.uPaths.value.dispose(); }
  }
}
/** A black hole: `blackHole(renderer, {sky, disc, inner, outer, temperature, tint, brightness, doppler, opacity,
 * speed, ring, tilt, lens, stars, seed, quality, skyGain})`; DESIGN.md §122.9. */
export const blackHole = (renderer, options = {}) => new BlackHole(renderer, options);

// ====================================================================================================
// Wormhole
// ====================================================================================================
/** Steps of the light path per pixel at each quality. */
export const WORMHOLE_STEPS = Object.freeze({fast: 24, normal: 36, fine: 72});
export const WORMHOLE_DEFAULTS = Object.freeze({sky: null, other: null, length: 0, rim: 0.1, rimColor: 0xbfd4ff, glow: 0.5, lens: 6, quality: "normal", skyGain: 1, otherGain: 2});
/** The radius of a wormhole's tube at the distance `l` along it (throat radius 1; `half`: half the length of its
 * straight middle): 1 inside the middle, then widening as sqrt(1 + (|l| - half)^2) (an Ellis wormhole's flare). */
export function wormholeRadius(l, half = 0) { const w = Math.max(Math.abs(l) - half, 0); return Math.sqrt(1 + w * w); }
/** One light path through or past a wormhole (throat radius 1), as the shader steps it: from the distance `l0`
 * along it (positive: our side), starting at `psi` radians from the outward direction: {side (1: it ends on our
 * side, -1: on the other), angle (how far round the wormhole it went, radians), b}. */
export function wormholePath(l0, psi, {half = 0, steps = 4000, k = 0.01, reach = 60} = {}) {
  const b = wormholeRadius(l0, half) * Math.sin(psi);
  let l = l0, dl = Math.cos(psi), phi = 0;
  const acc = (x) => { const w = Math.max(Math.abs(x) - half, 0), r2 = 1 + w * w; return (b * b * w * Math.sign(x)) / (r2 * r2); };
  for (let i = 0; i < steps; i++) {
    if (Math.abs(l) < half) { const ex = dl >= 0 ? 1 : -1; phi += (b * Math.abs(ex * half - l)) / Math.max(Math.abs(dl), 1e-6); l = ex * half; }
    const r = wormholeRadius(l, half), h = k * r, dh = dl + 0.5 * h * acc(l), ln = l + h * dh, rn = wormholeRadius(ln, half);
    phi += 0.5 * h * b * (1 / (r * r) + 1 / (rn * rn)); dl = dh + 0.5 * h * acc(ln); l = ln;
    if (rn > reach && dl * l > 0) return {side: l > 0 ? 1 : -1, angle: phi + Math.asin(Math.min(1, b / rn)), b};
  }
  return {side: l > 0 ? 1 : -1, angle: phi, b};
}

const WORMHOLE_FRAG = /* glsl */`
uniform samplerCube uSky, uOther; uniform mat3 uSkyTurn, uOtherTurn;
uniform float uLens, uHalf;
uniform vec4 uGain;     // our sky's gain, the other sky's, the rim's light, the walls' glow
uniform vec4 uTravel;   // on, the camera's distance along the wormhole, 0, 0
uniform vec3 uAxis, uRim;
varying vec3 vDir, vEye, vAxisX, vAxisY;
${DISPLAY}
const float PI = 3.14159265;
void main() {
  vec3 d = normalize(vDir);
  float r0 = length(vEye);
  vec3 e = uTravel.x > 0.5 ? uAxis : vEye / r0;
  float l = uTravel.x > 0.5 ? uTravel.y : uHalf + sqrt(max(r0 * r0 - 1.0, 0.0)), from = l >= 0.0 ? 1.0 : -1.0;
  float w0 = max(abs(l) - uHalf, 0.0), rc = sqrt(1.0 + w0 * w0);
  float c = dot(d, e); vec3 q = d - c * e; float sp = max(length(q), 1e-5); vec3 t = q / sp;
  float b = rc * sp, psi = atan(sp, c), dl = c, phi = 0.0, done = 0.0, r = rc, wound = 0.0;
  // from far away: straight to the lens's ball first (space is all but flat out there)
  if (rc > uLens) {
    float bb = min(b, uLens * 0.9999);
    phi = asin(bb / uLens) - asin(bb / rc); l = from * (uHalf + sqrt(uLens * uLens - 1.0)); dl = -from * sqrt(1.0 - bb * bb / (uLens * uLens));
  }
  float b2 = b * b;
  for (int i = 0; i < STEPS; i++) {
    if (done < 0.5) {
      // the straight middle in one stride: the path winds round it evenly
      if (abs(l) < uHalf) { float ex = dl >= 0.0 ? 1.0 : -1.0; wound = b * abs(ex * uHalf - l) / max(abs(dl), 1e-4); phi += wound; l = ex * uHalf; }
      float sg = l >= 0.0 ? 1.0 : -1.0, w = max(abs(l) - uHalf, 0.0), r2 = 1.0 + w * w, h = STRIDE * sqrt(r2);
      float dh = dl + 0.5 * h * b2 * w * sg / (r2 * r2), ln = l + h * dh;
      float sn = ln >= 0.0 ? 1.0 : -1.0, wn = max(abs(ln) - uHalf, 0.0), rn2 = 1.0 + wn * wn;
      phi += 0.5 * h * b * (1.0 / r2 + 1.0 / rn2);
      dl = dh + 0.5 * h * b2 * wn * sn / (rn2 * rn2); l = ln; r = sqrt(rn2);
      if (r > uLens && dl * sn > 0.0) done = 1.0;
    }
  }
  float side = l >= 0.0 ? 1.0 : -1.0, out_ = phi + done * asin(min(b / r, 1.0));
  // a ray that comes back to the camera's side: toward the lens's edge its bending is eased out
  float straight = from > 0.0 ? psi : PI - psi, ease = 1.0 - smoothstep(0.5 * uLens, uLens, b);
  float turn = side * from > 0.0 ? straight + (out_ - straight) * ease : out_;
  vec3 ours = textureCube(uSky, uSkyTurn * (cos(turn) * e + sin(turn) * t)).rgb * uGain.x;
  vec3 theirs = textureCube(uOther, uOtherTurn * (-cos(turn) * e + sin(turn) * t)).rgb * uGain.y;
  vec3 col = side > 0.0 ? ours : theirs;
  // the mouth's rim, where both skies are wound up endlessly: a thin line of light, never under a pixel wide
  float fw = max(fwidth(b), 1e-4), sigma = max(0.012, 0.8 * fw);
  col += uRim * uGain.z * (0.012 / sigma) * exp(-0.5 * pow((b - 1.0) / sigma, 2.0)) * step(uLens * 0.2, rc);
  // inside the straight middle: a faint light on the walls, stronger where the path winds round more (a depth cue, not physics)
  col += uRim * uGain.w * 0.05 * (1.0 - exp(-0.1 * wound));
  float edge = 1.0 - smoothstep(0.84 * uLens, uLens, b);
  gl_FragColor = vec4(finished(col) * edge, edge);
}`;

/** A wormhole: a ball that shows another sky. `object` (add it to the scene; one unit = the mouth's radius:
 * scale it), `passage(camera, progress, options)` flies a camera through, `release()`, `state`, `options`, `dispose()`. */
export class Wormhole {
  constructor(renderer, options = {}) {
    needRenderer("wormhole(renderer, options)", renderer);
    const o = this.options = resolve("wormhole", options, WORMHOLE_DEFAULTS);
    choice("wormhole: quality", o.quality, QUALITIES);
    number("wormhole: length", o.length, 0, 200); number("wormhole: lens", o.lens, 3, 40); number("wormhole: rim", o.rim, 0, 16); number("wormhole: glow", o.glow, 0, 16);
    number("wormhole: skyGain", o.skyGain, 0, 64); number("wormhole: otherGain", o.otherGain, 0, 64);
    this.renderer = renderer;
    this._sky = skyOf("wormhole: sky", o.sky, true); this._other = skyOf("wormhole: other", o.other, true);
    const u = this.uniforms = {uSky: {value: this._sky.texture}, uOther: {value: this._other.texture}, uSkyTurn: {value: new THREE.Matrix3()}, uOtherTurn: {value: new THREE.Matrix3()},
      uLens: {value: o.lens}, uHalf: {value: o.length / 2}, uGain: {value: new THREE.Vector4()}, uTravel: {value: new THREE.Vector4()}, uAxis: {value: new THREE.Vector3(0, 0, 1)},
      uRim: {value: new THREE.Vector3(...new THREE.Color(o.rimColor).toArray())}, uDisplay: {value: 0}};
    // a stride of 0.3 radii a step at "normal": the shorter the stride the more steps it takes to cross the lens
    this.material = new THREE.ShaderMaterial({...LENS_MATERIAL, defines: {STEPS: WORMHOLE_STEPS[o.quality], STRIDE: (0.3 * 36 / WORMHOLE_STEPS[o.quality]).toFixed(4)}, uniforms: u, vertexShader: LENS_VERT, fragmentShader: WORMHOLE_FRAG});
    this.object = lensQuad(this.material, o.lens);
    this.object.name = "wormhole";
    /** After passage(): {progress, l (the camera's distance along the wormhole in mouth radii, negative on the other side), side (1 | -1), inside (the wormhole fills the frame)}. */
    this.state = {progress: null, l: null, side: 1, inside: false};
    this.object.onBeforeRender = (r) => {
      u.uDisplay.value = toCanvas(r);
      u.uGain.value.set(o.skyGain * skyState(this._sky, u.uSkyTurn.value), o.otherGain * skyState(this._other, u.uOtherTurn.value), o.rim, o.glow);
      this.material.uniformsNeedUpdate = true;
    };
  }
  /** Fly `camera` through the wormhole: at `progress` 0 it stands at `from` (a world position on our side, default
   * where the camera is at the first call), at 0.5 in the middle of the throat, at 1 as far out on the other
   * side, moving straight along the line through the centre. Returns `state`: when `state.side` is -1 the camera is
   * under the other sky (show that sky and hide this side's things). `look: false` leaves the camera's aim alone. */
  passage(camera, progress, {from = null, look = true} = {}) {
    number("wormhole.passage: progress", progress, 0, 1);
    this.object.updateWorldMatrix(true, false);
    const centre = new THREE.Vector3().setFromMatrixPosition(this.object.matrixWorld), scale = this.object.matrixWorld.getMaxScaleOnAxis();
    if (from !== null) this._from = new THREE.Vector3(...vector("wormhole.passage: from", from));
    this._from ??= camera.getWorldPosition(new THREE.Vector3());
    const axis = this._from.clone().sub(centre), d = axis.length() / scale, half = this.options.length / 2;
    if (!(d > 1)) throw fail("wormhole.passage: `from` must be outside the mouth (farther from the centre than its radius)");
    axis.normalize();
    const start = half + Math.sqrt(d * d - 1), l = start * (1 - 2 * progress), side = l >= 0 ? 1 : -1, r = wormholeRadius(l, half);
    camera.position.copy(centre).addScaledVector(axis, side * r * scale);
    if (look) camera.lookAt(camera.position.clone().addScaledVector(axis, -1));
    camera.updateMatrixWorld();
    this.uniforms.uAxis.value.copy(axis); this.uniforms.uTravel.value.set(1, l, 0, 0);
    this.state = {progress, l, side, inside: r < this.options.lens};
    return this.state;
  }
  /** Back to a ball seen from outside by a camera on our side (after passage()). */
  release() { this.uniforms.uTravel.value.set(0, 0, 0, 0); this._from = null; this.state = {progress: null, l: null, side: 1, inside: false}; return this; }
  update() { return this; }
  dispose() {
    this.object.removeFromParent(); this.object.geometry.dispose(); this.material.dispose();
    for (const s of [this._sky, this._other]) if (s.own) s.texture.dispose();
  }
}
/** A wormhole: `wormhole(renderer, {sky, other, length, rim, rimColor, glow, lens, quality, skyGain, otherGain})`; DESIGN.md §122.9. */
export const wormhole = (renderer, options = {}) => new Wormhole(renderer, options);

// ====================================================================================================
// Warp
// ====================================================================================================
export const WARP_DEFAULTS = Object.freeze({seed: 1, count: 2600, depth: 600, radius: 70, speed: 2, seconds: 4, fps: 30, shutter: 4, tunnel: 1, flash: 1,
  color: 0xbcd0ff, ahead: 0x7fb0ff, behind: 0xff7a4a, quality: "normal"});
const WARP_COUNT = Object.freeze({fast: 0.5, normal: 1, fine: 2});
/** The marks of a jump on its progress 0..1: the stars stretch until `enter`, the tunnel lasts until `leave`, by `out` the stars are points again. */
export const WARP_MARKS = Object.freeze({enter: 0.14, leave: 0.84, out: 0.96});
const WARP_TABLE = (() => {
  // the distance flown (the integral of the speed) at 1,025 points of the progress
  const n = 1024, table = new Float64Array(n + 1);
  for (let i = 1; i <= n; i++) table[i] = table[i - 1] + (warpSpeed((i - 0.5) / n)) / n;
  return table;
})();
/** The speed of a jump at progress p (0..1), from 0 to 1: a slow start that runs away, full speed in the tunnel, a quick braking. */
export function warpSpeed(p) {
  const up = smooth(0, WARP_MARKS.enter, p), down = 1 - smooth(WARP_MARKS.leave, WARP_MARKS.out, p);
  return up * up * up * down * down;
}
/** A jump at progress p (0..1): {speed (0..1), travel (the distance flown, in tunnel-seconds at full speed: its
 * integral), flash (0..1: the burst of light on entering and, weaker, on leaving), tunnel (0..1: the tunnel's
 * glow), sky (0..1: how bright the ordinary sky should be drawn: pass it to sky.set({brightness}))}. A pure function. */
export function warpAt(p) {
  const q = clamp01(p), x = q * 1024, i = Math.min(1023, Math.floor(x)), travel = WARP_TABLE[i] + (WARP_TABLE[i + 1] - WARP_TABLE[i]) * (x - i);
  const bump = (at, rise, fall) => (q < at ? smooth(at - rise, at, q) : 1 - smooth(at, at + fall, q));
  const flash = Math.max(bump(WARP_MARKS.enter, 0.05, 0.09), 0.6 * bump(WARP_MARKS.out - 0.03, 0.05, 0.08));
  const tunnel = smooth(WARP_MARKS.enter - 0.03, WARP_MARKS.enter + 0.1, q) * (1 - smooth(WARP_MARKS.leave - 0.02, WARP_MARKS.out - 0.02, q));
  const sky = 1 - smooth(0.04, WARP_MARKS.enter, q) * (1 - smooth(WARP_MARKS.out - 0.06, 1, q));
  return {speed: warpSpeed(q), travel, flash, tunnel, sky};
}
/** How long (in depths of the star volume) a streak is at progress p: what a star flies in `shutter` frames,
 * so that streaks of following frames overlap and nothing flickers. */
export function warpStreak(p, {speed = WARP_DEFAULTS.speed, seconds = WARP_DEFAULTS.seconds, fps = WARP_DEFAULTS.fps, shutter = WARP_DEFAULTS.shutter} = {}) {
  const step = shutter / (seconds * fps);
  return (warpAt(p).travel - warpAt(Math.max(0, p - step)).travel) * speed * seconds;
}

const WARP_STAR_VERT = /* glsl */`
attribute vec4 aStar;   // angle, distance from the axis, place along it (0..1), tone
uniform vec4 uWarp;     // the way flown (depths), a streak's length (depths), speed (0..1), gain
uniform vec4 uBox;      // the volume's depth, the px size of a spot (sigma), 2 / width, 2 / height
uniform float uThin;
uniform vec3 uColor, uAhead, uBehind;
varying vec3 vUV; varying vec3 vLight;
void main() {
  float z = fract(aStar.z + uWarp.x), head = (z - 0.9) * uBox.x, tail = head - max(uWarp.y * uBox.x, 1e-3);
  vec2 off = aStar.y * vec2(cos(aStar.x), sin(aStar.x));
  vec3 a = (modelViewMatrix * vec4(off, tail, 1.0)).xyz, b = (modelViewMatrix * vec4(off, head, 1.0)).xyz;
  // keep both ends before the camera
  float near = -0.5, shown = 1.0;
  if (a.z > near && b.z > near) shown = 0.0;
  else if (b.z > near) b = mix(a, b, (near - a.z) / (b.z - a.z));
  else if (a.z > near) a = mix(b, a, (near - b.z) / (a.z - b.z));
  vec4 ca = projectionMatrix * vec4(a, 1.0), cb = projectionMatrix * vec4(b, 1.0);
  vec2 pa = ca.xy / ca.w / uBox.zw, pb = cb.xy / cb.w / uBox.zw, along = pb - pa;
  float len = length(along), sigma = uBox.y, reach = 3.0 * sigma;
  vec2 dir = len > 1e-3 ? along / len : vec2(1.0, 0.0), nor = vec2(-dir.y, dir.x);
  vec2 p = mix(pa, pb, position.x) + dir * (position.x * 2.0 - 1.0) * reach + nor * position.y * reach;
  vUV = vec3(mix(-reach, len + reach, position.x), position.y * reach, len);
  // bluer ahead, redder behind, the more the faster
  float toward = normalize(off.xyy * vec3(1.0, 1.0, 0.0) + vec3(0.0, 0.0, head)).z * -1.0;
  vec3 tint = mix(uColor * mix(vec3(1.0, 0.86, 0.7), vec3(0.8, 0.9, 1.0), aStar.w), toward > 0.0 ? uAhead : uBehind, uWarp.z * 0.8 * smoothstep(0.8, 0.99, abs(toward)));
  // a streak keeps a share of its star's light as it grows; new stars fade in far away, old ones fade out behind
  float amp = (0.25 + 1.6 * aStar.w * aStar.w) * uWarp.w * uThin / sqrt(1.0 + len / (5.0 * sigma));
  vLight = tint * amp * smoothstep(0.08, 0.6, z) * (1.0 - smoothstep(0.93, 1.0, z)) * shown;
  gl_Position = vec4(p * uBox.zw, 0.0, 1.0);
}`;
const WARP_STAR_FRAG = /* glsl */`
varying vec3 vUV; varying vec3 vLight; uniform vec4 uBox;
${DISPLAY}
void main() {
  float s = uBox.y, x = vUV.x, len = vUV.z, dx = x < 0.0 ? x : max(x - len, 0.0);
  float across = exp(-0.5 * (vUV.y * vUV.y + dx * dx) / (s * s));
  // a little brighter toward the head, with soft ends: an even line has no bright spot that would jump from frame to frame
  float t = clamp(x / max(len, 1e-3), 0.0, 1.0), body = mix(1.0, (0.55 + 0.45 * t) * smoothstep(0.0, 0.25, t) * (1.0 - smoothstep(0.8, 1.0, t)), smoothstep(2.0, 12.0, len));
  gl_FragColor = vec4(display(vLight * across * body), 1.0);
}`;
const WARP_TUNNEL_FRAG = /* glsl */`
uniform sampler2D uNoise; uniform vec4 uWarp; uniform vec4 uTunnel;   // glow, turn, 0, 0
uniform vec3 uColor, uAhead;
varying vec2 vUv;
${DISPLAY}
void main() {
  // long soft bands that run along the tunnel, slower than the stars, and finer threads inside them
  float way = uWarp.x * 0.3;
  float broad = texture2D(uNoise, vec2(vUv.x * 3.0 + uTunnel.y, vUv.y * 0.35 - way * 0.35)).r;
  float thread = texture2D(uNoise, vec2(vUv.x * 9.0 - uTunnel.y * 0.5, vUv.y * 0.6 - way * 0.6 + 0.37)).g;
  float band = smoothstep(0.35, 0.85, broad) * (0.35 + 0.65 * smoothstep(0.3, 0.8, thread));
  // far away the walls close into the light ahead; near the camera they fade out
  float far = 1.0 - vUv.y, depth = smoothstep(0.0, 0.25, far) * (1.0 - smoothstep(0.86, 1.0, far));
  vec3 col = mix(uAhead * 0.5, uColor, band) * (0.012 + 0.15 * band) * depth * uTunnel.x * (uDisplay > 0.5 ? 0.5 : 1.0);
  gl_FragColor = vec4(display(col), 1.0);
}`;
const WARP_GLOW_FRAG = /* glsl */`
uniform vec4 uGlow;   // the light ahead, the flash's veil over the whole frame, the flash's burst ahead, 0
uniform vec3 uColor;
varying vec2 vUv;
${DISPLAY}
void main() {
  vec2 p = vUv * 2.0 - 1.0; float r2 = dot(p, p);
  vec3 col = uColor * (uGlow.x * (0.7 * exp(-r2 * 60.0) + 0.12 * exp(-r2 * 6.0)) + uGlow.z * (0.5 * exp(-r2 * 30.0) + 0.3 * exp(-r2 * 3.5))) * (1.0 - smoothstep(0.7, 1.0, sqrt(r2))) * (uDisplay > 0.5 ? 0.4 : 1.0);
  gl_FragColor = vec4(display(col), 1.0);
}`;
const PLAIN_VERT = "varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }";
const SCREEN_VERT = "varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }";
const FLASH_FRAG = /* glsl */`
uniform vec4 uGlow; uniform vec3 uColor; varying vec2 vUv;
${DISPLAY}
void main() { vec2 p = vUv * 2.0 - 1.0; gl_FragColor = vec4(display(mix(vec3(1.0), uColor, 0.35) * uGlow.y * (1.0 - 0.25 * dot(p, p))), 1.0); }`;
function noiseTexture(seed, size = 256, cells = 8) {
  const data = new Uint8Array(size * size * 4), a = lattice(seed), b = lattice(seed + 7);
  for (let j = 0; j < size; j++) for (let i = 0; i < size; i++) {
    const x = (i / size) * cells, y = (j / size) * cells, k = (j * size + i) * 4;
    const wrap = (at, fx, fy, c) => { const y0 = Math.floor(fy), f = fy - y0, s = f * f * (3 - 2 * f); return noise2(at, fx, ((y0 % c) + c) % c, c) * (1 - s) + noise2(at, fx, (y0 + 1) % c, c) * s; };
    data[k] = Math.round(255 * (0.65 * wrap(a, x, y, cells) + 0.35 * wrap(a, x * 2 + 3.3, y * 2, cells * 2)));
    data[k + 1] = Math.round(255 * (0.6 * wrap(b, x * 2, y * 2, cells * 2) + 0.4 * wrap(b, x * 4 + 1.7, y * 4, cells * 4)));
    data[k + 2] = 0; data[k + 3] = 255;
  }
  const t = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.magFilter = THREE.LinearFilter; t.minFilter = THREE.LinearMipmapLinearFilter; t.generateMipmaps = true; t.needsUpdate = true;
  return t;
}

/** A jump to warp: stars that stretch into streaks from the point flown at, a flash, a tunnel, and back.
 * `object` (add it to the scene), `update(t, {progress, camera, direction, intensity})`, `state`, `dispose()`. */
export class Warp {
  constructor(renderer, options = {}) {
    needRenderer("warp(renderer, options)", renderer);
    const o = this.options = resolve("warp", options, WARP_DEFAULTS);
    choice("warp: quality", o.quality, QUALITIES);
    number("warp: count", o.count, 1, 40000); number("warp: depth", o.depth, 10, 1e6); number("warp: radius", o.radius, 1, 1e6); number("warp: speed", o.speed, 0.05, 50);
    number("warp: seconds", o.seconds, 0.2, 600); number("warp: fps", o.fps, 1, 240); number("warp: shutter", o.shutter, 1, 16); number("warp: tunnel", o.tunnel, 0, 16); number("warp: flash", o.flash, 0, 4);
    this.renderer = renderer;
    const n = Math.round(o.count * WARP_COUNT[o.quality]), random = rng(o.seed), star = new Float32Array(n * 4);
    for (let i = 0; i < n; i++) star.set([random() * TAU, o.radius * Math.sqrt(0.004 + 0.996 * random()), random(), random()], i * 4);
    const quad = new THREE.PlaneGeometry(1, 2); quad.translate(0.5, 0, 0);
    const geometry = this.geometry = new THREE.InstancedBufferGeometry();
    geometry.index = quad.index; geometry.setAttribute("position", quad.getAttribute("position"));
    geometry.setAttribute("aStar", new THREE.InstancedBufferAttribute(star, 4)); geometry.instanceCount = n;
    const color = (c) => ({value: new THREE.Vector3(...new THREE.Color(c).toArray())});
    const u = this.uniforms = {uWarp: {value: new THREE.Vector4()}, uBox: {value: new THREE.Vector4(o.depth, 1, 1, 1)}, uColor: color(o.color), uAhead: color(o.ahead), uBehind: color(o.behind),
      uThin: {value: 1}, uNoise: {value: noiseTexture(o.seed)}, uTunnel: {value: new THREE.Vector4()}, uGlow: {value: new THREE.Vector4()}, uDisplay: {value: 0}};
    const common = {uniforms: u, blending: THREE.AdditiveBlending, transparent: true, depthTest: false, depthWrite: false, toneMapped: false, fog: false};
    const view = new THREE.Vector4();
    const before = (material) => (r) => {
      r.getCurrentViewport(view);
      // a spot's width follows the frame's height as the sky's stars do, never under 0.62 px
      // (in a small frame, where it would be, its light is thinned instead; straight to the canvas, where light adds up after the tone curve, all of it is turned down)
      const natural = 0.8 * view.w / 720, sigma = Math.max(0.62, natural);
      u.uBox.value.set(o.depth, sigma, 2 / view.z, 2 / view.w); u.uDisplay.value = toCanvas(r); u.uThin.value = Math.pow(natural / sigma, 1.6) * (u.uDisplay.value ? 0.5 : 1); material.uniformsNeedUpdate = true;
    };
    const mesh = (geo, material, order) => { const m = new THREE.Mesh(geo, material); m.frustumCulled = false; m.renderOrder = order; m.onBeforeRender = before(material); return m; };
    this.stars = mesh(geometry, new THREE.ShaderMaterial({...common, vertexShader: WARP_STAR_VERT, fragmentShader: WARP_STAR_FRAG}), -940);
    const tube = new THREE.CylinderGeometry(o.radius * 0.55, o.radius * 0.55, o.depth, 48, 1, true); tube.rotateX(-Math.PI / 2); tube.translate(0, 0, -o.depth * 0.4);
    this.tunnel = mesh(tube, new THREE.ShaderMaterial({...common, side: THREE.BackSide, vertexShader: PLAIN_VERT, fragmentShader: WARP_TUNNEL_FRAG}), -950);
    const far = new THREE.PlaneGeometry(o.radius * 3, o.radius * 3); far.translate(0, 0, -o.depth * 0.9);
    this.glow = mesh(far, new THREE.ShaderMaterial({...common, vertexShader: PLAIN_VERT, fragmentShader: WARP_GLOW_FRAG}), -945);
    this.flash = mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({...common, vertexShader: SCREEN_VERT, fragmentShader: FLASH_FRAG}), 9000);
    this.flash.userData.overlay = true;
    this.object = new THREE.Group(); this.object.name = "warp"; this.object.add(this.tunnel, this.glow, this.stars, this.flash);
    /** After update(): warpAt(progress) and `intensity`. */
    this.state = {...warpAt(0), progress: 0, intensity: 1};
    this.update(0, {progress: 0});
  }
  /** Set the jump to `progress` (0..1; a function of the page's time, so it locks to bars) round `camera`, flying
   * along `direction` (default: where the camera looks). `intensity` (default 1; from the music) scales the
   * streaks' and the tunnel's light; the picture is never zoomed. Returns `state` (use state.sky for the sky's brightness). */
  update(t, {progress = null, camera = null, direction = null, intensity = 1} = {}) {
    const o = this.options, p = progress === null ? clamp01(t / o.seconds) : number("warp.update: progress", progress, 0, 1), s = warpAt(p), u = this.uniforms;
    number("warp.update: intensity", intensity, 0, 16);
    if (camera) {
      camera.updateWorldMatrix(true, false);
      camera.getWorldPosition(this.object.position);
      const to = direction ? new THREE.Vector3(...vector("warp.update: direction", direction)).normalize() : camera.getWorldDirection(new THREE.Vector3());
      this.object.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, -1), to);
    }
    const base = 0.35 + 0.65 * s.speed;
    u.uWarp.value.set(s.travel * o.speed * o.seconds + 0.02 * t, Math.max(warpStreak(p, o), 0), s.speed, base * intensity * smooth(0.02, 0.1, p) * (1 - smooth(0.93, 1, p)));
    u.uTunnel.value.set(o.tunnel * s.tunnel * intensity, 0.013 * t, 0, 0);
    // the flash is a burst of the light ahead and a faint veil over the frame
    u.uGlow.value.set(o.tunnel * s.tunnel * (0.6 + 0.4 * intensity) * 2.2, o.flash * s.flash * 0.07, o.flash * s.flash * 5, 0);
    this.tunnel.visible = s.tunnel > 0.001; this.glow.visible = s.tunnel > 0.001 || s.flash > 0.001; this.flash.visible = s.flash > 0.001;
    this.state = {...s, progress: p, intensity};
    return this.state;
  }
  dispose() {
    this.object.removeFromParent(); this.geometry.dispose(); this.uniforms.uNoise.value.dispose();
    for (const m of [this.stars, this.tunnel, this.glow, this.flash]) { m.material.dispose(); if (m.geometry !== this.geometry) m.geometry.dispose(); }
  }
}
/** A jump to warp: `warp(renderer, {seed, count, depth, radius, speed, seconds, fps, shutter, tunnel, flash, color, ahead, behind, quality})`; DESIGN.md §122.9. */
export const warp = (renderer, options = {}) => new Warp(renderer, options);

// ====================================================================================================
// Asteroids
// ====================================================================================================
function lattice3(seed) {
  const random = rng(seed), table = new Float32Array(4096);
  for (let i = 0; i < 4096; i++) table[i] = random();
  return (x, y, z) => table[(Math.imul(x, 73856093) ^ Math.imul(y, 19349663) ^ Math.imul(z, 83492791)) & 4095];
}
// smooth noise 0..1 in space
function noise3(at, x, y, z) {
  const x0 = Math.floor(x), y0 = Math.floor(y), z0 = Math.floor(z), fx = x - x0, fy = y - y0, fz = z - z0;
  const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy), sz = fz * fz * (3 - 2 * fz);
  const row = (j, k) => { const a = at(x0, y0 + j, z0 + k); return a + (at(x0 + 1, y0 + j, z0 + k) - a) * sx; };
  const face = (k) => { const a = row(0, k); return a + (row(1, k) - a) * sy; };
  const a = face(0);
  return a + (face(1) - a) * sz;
}
function seededUnit(random) { const z = 2 * random() - 1, a = TAU * random(), s = Math.sqrt(1 - z * z); return [s * Math.cos(a), s * Math.sin(a), z]; }

/** The shape of a rock from a seed: a function from a unit direction to {point: [x, y, z] (the surface there;
 * the longest half-axis about 1), shade (0..1: darker in crater floors and hollows)}. Lumps at three scales,
 * `craters` bowls with raised rims (many small, few large), up to four flat facets where a piece broke off. */
export function rockShape(seed, {craters = 14, detail = 1} = {}) {
  const random = rng(seed), at = lattice3(seed + 17), axes = [1, 0.6 + 0.32 * random(), 0.48 + 0.3 * random()], o = [random() * 50, random() * 50, random() * 50];
  const bowls = [], cuts = [];
  for (let i = 0; i < craters; i++) { const size = 0.09 + 0.45 * Math.pow(random(), 2.4); bowls.push({dir: seededUnit(random), cos: Math.cos(size * 1.5), size, depth: size * (0.2 + 0.18 * random())}); }
  for (let i = 0, n = 1 + Math.floor(random() * 3); i < n; i++) cuts.push({n: seededUnit(random), h: 0.62 + 0.25 * random()});
  return (d) => {
    let r = 1 + 0.5 * (noise3(at, d[0] * 1.2 + o[0], d[1] * 1.2 + o[1], d[2] * 1.2 + o[2]) - 0.5) + 0.22 * (noise3(at, d[0] * 2.9 + o[1], d[1] * 2.9 + o[2], d[2] * 2.9 + o[0]) - 0.5);
    let fine = 0.1 * (noise3(at, d[0] * 6.3 + o[2], d[1] * 6.3 + o[0], d[2] * 6.3 + o[1]) - 0.5);
    if (detail > 1) fine += 0.045 * (noise3(at, d[0] * 14 + o[0], d[1] * 14 + o[1], d[2] * 14 + o[2]) - 0.5) + 0.02 * (noise3(at, d[0] * 31 + o[1], d[1] * 31 + o[0], d[2] * 31 + o[2]) - 0.5);
    let shade = 0.5 + 4 * fine;
    r += fine;
    for (const b of bowls) {
      const c = d[0] * b.dir[0] + d[1] * b.dir[1] + d[2] * b.dir[2];
      if (c < b.cos) continue;
      const x = Math.acos(Math.min(1, c)) / b.size, rim = Math.exp(-((x - 1) * (x - 1)) / 0.045);
      r += b.depth * (x < 1 ? -(1 - x * x) * (1 - 0.25 * rim) + 0.3 * rim : 0.3 * rim);
      shade += x < 1 ? -0.3 * (1 - x * x) + 0.25 * rim : 0.25 * rim;
    }
    let p = [d[0] * r * axes[0], d[1] * r * axes[1], d[2] * r * axes[2]];
    // a facet: what sticks out past a plane is pressed nearly flat (it keeps a little of its relief)
    for (const c of cuts) { const over = (p[0] * c.n[0] + p[1] * c.n[1] + p[2] * c.n[2] - c.h) * 0.88; if (over > 0) { p = [p[0] - over * c.n[0], p[1] - over * c.n[1], p[2] - over * c.n[2]]; shade += 0.1; } }
    return {point: p, shade: clamp01(shade)};
  };
}
/** A rock as a geometry (positions, normals, vertex colours for the ground's light and dark): `detail` is
 * three's icosahedron detail (0: 20 faces, 2: 180, 6: 980, 56: 65,000); `smooth: false` leaves the faces flat (facets). */
export function rockGeometry(seed, detail = 6, {smooth: rounded = false, craters = 14} = {}) {
  const geometry = new THREE.IcosahedronGeometry(1, detail), position = geometry.getAttribute("position"), n = position.count;
  const shape = rockShape(seed, {craters, detail: detail > 12 ? 2 : 1}), color = new Float32Array(n * 3), normal = rounded ? new Float32Array(n * 3) : null;
  for (let i = 0; i < n; i++) {
    const d = unit([position.getX(i), position.getY(i), position.getZ(i)]), s = shape(d), tone = 0.5 + 0.75 * s.shade;
    if (rounded) {
      // the surface's own normal from two near points, so facets of the mesh do not show
      const side = unit(cross(d, Math.abs(d[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0])), up = cross(d, side), e = 0.004;
      const a = shape(unit([d[0] + e * side[0], d[1] + e * side[1], d[2] + e * side[2]])).point, b = shape(unit([d[0] + e * up[0], d[1] + e * up[1], d[2] + e * up[2]])).point;
      let nn = unit(cross([a[0] - s.point[0], a[1] - s.point[1], a[2] - s.point[2]], [b[0] - s.point[0], b[1] - s.point[1], b[2] - s.point[2]]));
      if (dot(nn, d) < 0) nn = [-nn[0], -nn[1], -nn[2]];
      normal.set(nn, i * 3);
    }
    position.setXYZ(i, s.point[0], s.point[1], s.point[2]); color.set([tone, tone, tone], i * 3);
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(color, 3));
  if (rounded) geometry.setAttribute("normal", new THREE.BufferAttribute(normal, 3)); else geometry.computeVertexNormals();
  geometry.deleteAttribute("uv");
  geometry.computeBoundingSphere(); geometry.computeBoundingBox();
  return geometry;
}
/** The radius of rock number u (0..1 of them) when sizes follow a power law between `least` and `most`
 * (the number of rocks larger than r falls as r^-power: many small, few large). */
export function rockRadius(u, least, most, power = 2.3) { return least * Math.pow(1 - u * (1 - Math.pow(least / most, power)), -1 / power); }
/** A sphere's brightness at phase angle `alpha` (radians between the sun and the camera seen from it), 1 when full. */
export function phaseOfSphere(alpha) { return (Math.sin(alpha) + (Math.PI - alpha) * Math.cos(alpha)) / Math.PI; }

export const ASTEROID_DEFAULTS = Object.freeze({seed: 1, detail: 64, craters: 40, color: 0x777067, roughness: 0.96, spin: 40, axis: [0.2, 1, 0.1]});
/** One asteroid for a close-up: `object` (a mesh of radius about 1 that casts and takes shadows: scale it),
 * `update(t)` (it turns once in `spin` seconds about `axis`), `dispose()`. Lit by the scene's lights. */
export class Asteroid {
  constructor(options = {}) {
    const o = this.options = resolve("asteroid", options, ASTEROID_DEFAULTS);
    number("asteroid: detail", o.detail, 1, 120); number("asteroid: craters", o.craters, 0, 200); number("asteroid: seed", o.seed, 0, 1e9);
    this.axis = new THREE.Vector3(...vector("asteroid: axis", o.axis)).normalize();
    this.geometry = rockGeometry(o.seed, Math.round(o.detail), {smooth: true, craters: o.craters});
    this.material = new THREE.MeshStandardMaterial({color: o.color, roughness: o.roughness, metalness: 0, vertexColors: true});
    this.object = new THREE.Mesh(this.geometry, this.material);
    this.object.castShadow = this.object.receiveShadow = true; this.object.name = "asteroid";
    this.update(0);
  }
  update(t) { const o = this.options; this.object.quaternion.setFromAxisAngle(this.axis, o.spin ? (TAU * t) / o.spin : 0); return this; }
  dispose() { this.object.removeFromParent(); this.geometry.dispose(); this.material.dispose(); }
}
/** One asteroid for a close-up: `asteroid({seed, detail, craters, color, roughness, spin, axis})`. */
export const asteroid = (options = {}) => new Asteroid(options);

export const ASTEROIDS_DEFAULTS = Object.freeze({layout: "field", seed: 1, count: null, size: 120, least: null, most: null, power: 1.8, shapes: 4, rocks: 800, follow: true, tumble: 1, glint: null,
  color: 0x777067, variety: 0.4, albedo: 0.18, brightness: 1, dust: 0.5, inner: 60, outer: 100, thickness: 4, rate: 0.01, gaps: 2, eccentricity: 0.06, light: null, sun: [1, 0.3, 0.5], quality: "normal"});
const ROCK_LODS = Object.freeze([{detail: 10, over: 26, smooth: true}, {detail: 3, over: 7, smooth: true}, {detail: 1, over: 1.7, smooth: false}]);
const ROCK_SHARE = Object.freeze({fast: 0.5, normal: 1, fine: 2});
/** Where the rocks of a belt are, in belt radii 0..1 from inner to outer: the density at `x` with `gaps` cleared lanes from the seed. */
export function beltDensity(x, lanes) {
  let d = smooth(0, 0.12, x) * (1 - smooth(0.85, 1, x));
  for (const g of lanes) d *= 1 - 0.92 * Math.exp(-((x - g.at) * (x - g.at)) / (2 * g.width * g.width));
  return d;
}
const ROCK_POINT_VERT = /* glsl */`
attribute vec4 aRock;    // radius, shown (0..1), tint, 0
uniform vec4 uView;      // focal length in px, the px size of a spot (sigma), gain, glint
uniform vec4 uRocks;     // the largest radius, 1: the sun is at the object's middle, 0, 0
uniform vec3 uSun, uSunColor, uColor;
varying vec3 vLight; varying float vHalf;
void main() {
  vec4 world = modelMatrix * vec4(position, 1.0), eye = viewMatrix * world;
  float dist = max(length(eye.xyz), 1e-6), px = aRock.x * length(modelMatrix[0].xyz) * uView.x / dist, sigma = uView.y;
  // a far rock is a spot holding the light of its lit face; it fades as the mesh takes over
  vec3 sun = uRocks.y > 0.5 ? modelMatrix[3].xyz - world.xyz : uSun;
  float ca = dot(normalize(sun), normalize(cameraPosition - world.xyz)), alpha = acos(clamp(ca, -1.0, 1.0));
  float phase = (sin(alpha) + (3.14159265 - alpha) * ca) / 3.14159265;
  // (glint: a far rock is drawn brighter than its size would give, or a belt seen from afar would be black: a stated choice)
  float amp = uView.z * phase * (px * px / (2.0 * sigma * sigma) + uView.w * sqrt(aRock.x / uRocks.x)) * (1.0 - smoothstep(1.7, 3.2, px)) * aRock.y;
  vLight = uColor * mix(0.75, 1.25, aRock.z) * uSunColor * amp; vHalf = 3.0 * sigma;
  gl_PointSize = 2.0 * vHalf;
  gl_Position = amp > 2e-4 ? projectionMatrix * eye : vec4(2.0, 2.0, 2.0, 1.0);
}`;
const ROCK_POINT_FRAG = /* glsl */`
varying vec3 vLight; varying float vHalf; uniform vec4 uView;
${DISPLAY}
void main() {
  vec2 p = (gl_PointCoord - 0.5) * 2.0 * vHalf;
  gl_FragColor = vec4(display(vLight * exp(-dot(p, p) / (2.0 * uView.y * uView.y))), 1.0);
}`;
const BELT_DUST_FRAG = /* glsl */`
uniform sampler2D uLanes; uniform vec4 uDust;   // inner, outer, light, 0
uniform vec3 uColor, uSunColor; varying vec3 vAt;
${DISPLAY}
void main() {
  float x = (length(vAt.xz) - uDust.x) / (uDust.y - uDust.x);
  float d = texture2D(uLanes, vec2(clamp(x, 0.0, 1.0), 0.5)).r * step(0.0, x) * step(x, 1.0);
  gl_FragColor = vec4(display(uColor * uSunColor * d * uDust.z), 1.0);
}`;

/** Thousands of rocks: a field to fly through or a belt round a star or planet. `object` (add it to the scene),
 * `update(t, {camera, sun})`, `count`, `shown` (after update: how many are meshes), `dispose()`. The near
 * ones are meshes lit by the scene's lights, the far ones points lit by `sun`; a belt adds a band of dust. */
export class Asteroids {
  constructor(renderer, options = {}) {
    needRenderer("asteroids(renderer, options)", renderer);
    const o = this.options = resolve("asteroids", options, ASTEROIDS_DEFAULTS);
    choice("asteroids: layout", o.layout, ["field", "belt"]); choice("asteroids: quality", o.quality, QUALITIES);
    const belt = this.belt = o.layout === "belt";
    // sizes: a field's rocks are things to fly past; a belt's are specks beside its width
    o.least ??= belt ? o.outer * 0.0003 : 0.15; o.most ??= belt ? o.outer * 0.008 : 9; o.glint ??= belt ? 0.5 : 0.05;
    number("asteroids: least", o.least, 1e-9, 1e9); number("asteroids: most", o.most, o.least, 1e9); number("asteroids: power", o.power, 0.5, 6); number("asteroids: glint", o.glint, 0, 16);
    number("asteroids: shapes", o.shapes, 1, 8); number("asteroids: rocks", o.rocks, 0, 4000); number("asteroids: size", o.size, 1e-3, 1e12);
    number("asteroids: inner", o.inner, 1e-6, 1e12); number("asteroids: outer", o.outer, o.inner, 1e12); number("asteroids: thickness", o.thickness, 0, 60);
    const n = this.count = Math.round(number("asteroids: count", o.count ?? (belt ? 16000 : 3000), 1, 200000) * (belt ? ROCK_SHARE[o.quality] : 1));
    this.renderer = renderer;
    const random = rng(o.seed), shapes = Math.round(o.shapes);
    // every rock: where it is (a field: a place in the box; a belt: an orbit), its size, its turning
    this.radius = new Float32Array(n); this.base = new Float32Array(n * 4); this.turn = new Float32Array(n * 5); this.shapeOf = new Uint8Array(n);
    this.lanes = [];
    for (let i = 0; i < o.gaps; i++) this.lanes.push({at: 0.2 + 0.6 * random(), width: 0.012 + 0.02 * random()});
    const look = new Float32Array(n * 4), tints = new Float32Array(n * 3), base = new THREE.Color(o.color), hsl = {};
    base.getHSL(hsl);
    for (let i = 0; i < n; i++) {
      this.radius[i] = rockRadius(random(), o.least, o.most, o.power);
      if (belt) {
        let x = random();
        for (let tries = 0; tries < 12 && random() > beltDensity(x, this.lanes); tries++) x = random();
        const tilt = (o.thickness * Math.PI / 180) * (random() + random() + random() - 1.5) / 0.9;
        this.base.set([o.inner + (o.outer - o.inner) * x, random() * TAU, tilt, random() * TAU], i * 4);
      } else this.base.set([(random() - 0.5) * o.size, (random() - 0.5) * o.size, (random() - 0.5) * o.size, random()], i * 4);
      const axis = seededUnit(random);
      this.turn.set([axis[0], axis[1], axis[2], random() * TAU, o.tumble * (0.05 + 0.5 * random()) / Math.sqrt(Math.max(this.radius[i] / o.least, 1)) * 3], i * 5);
      this.shapeOf[i] = Math.floor(random() * shapes);
      const tone = random(), c = new THREE.Color().setHSL((hsl.h + 0.05 * o.variety * (random() - 0.5) + 1) % 1, clamp01(hsl.s * (1 + o.variety * (random() - 0.5))), clamp01(hsl.l * (1 + 1.2 * o.variety * (tone - 0.5))));
      tints.set([c.r, c.g, c.b], i * 3); look.set([this.radius[i], 1, tone, 0], i * 4);
    }
    this.tints = tints;
    this.object = new THREE.Group(); this.object.name = belt ? "asteroid belt" : "asteroid field";
    const reach = belt ? o.outer * 1.3 : o.size * (o.follow ? 1e3 : 0.9);
    // the meshes: every shape at three levels of detail
    this.material = new THREE.MeshStandardMaterial({color: 0xffffff, roughness: 0.96, metalness: 0, vertexColors: true});
    this.meshes = [];
    const cap = Math.max(1, Math.round(o.rocks));
    for (let s = 0; s < shapes; s++) this.meshes.push(ROCK_LODS.map((lod, k) => {
      const mesh = new THREE.InstancedMesh(rockGeometry(o.seed * 31 + s * 7 + 1, lod.detail, {smooth: lod.smooth}), this.material, Math.max(4, Math.ceil(cap / shapes * (k === 0 ? 0.1 : k === 1 ? 0.25 : 0.65))));
      mesh.count = 0; mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage); mesh.setColorAt(0, base); mesh.instanceColor.setUsage(THREE.DynamicDrawUsage);
      mesh.boundingSphere = new THREE.Sphere(new THREE.Vector3(), reach); mesh.name = `rocks ${s}/${k}`;
      this.object.add(mesh);
      return mesh;
    }));
    // the points
    this.positions = new Float32Array(n * 3); this.look = look;
    const geometry = this.geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(this.positions, 3).setUsage(THREE.DynamicDrawUsage));
    geometry.setAttribute("aRock", new THREE.BufferAttribute(look, 4).setUsage(THREE.DynamicDrawUsage));
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), reach);
    const u = this.uniforms = {uView: {value: new THREE.Vector4(1000, 1, 1, 0)}, uSun: {value: new THREE.Vector3(1, 0.3, 0.5)}, uSunColor: {value: new THREE.Vector3(1, 1, 1)},
      uColor: {value: new THREE.Vector3(...base.toArray())}, uRocks: {value: new THREE.Vector4(o.most, 0, 0, 0)}, uDust: {value: new THREE.Vector4(o.inner, o.outer, 0, 0)}, uLanes: {value: null}, uDisplay: {value: 0}};
    const view = new THREE.Vector4();
    const common = {uniforms: u, blending: THREE.AdditiveBlending, transparent: true, depthTest: true, depthWrite: false, toneMapped: false, fog: false};
    this.pointMaterial = new THREE.ShaderMaterial({...common, vertexShader: ROCK_POINT_VERT, fragmentShader: ROCK_POINT_FRAG});
    this.points = new THREE.Points(geometry, this.pointMaterial);
    this.points.onBeforeRender = (r, scene, camera) => {
      r.getCurrentViewport(view);
      u.uView.value.set(view.w / (2 * Math.tan((camera.fov ?? 40) * Math.PI / 360)), Math.max(0.62, 0.75 * view.w / 720), 0.9 * o.albedo / 0.18 * o.brightness, o.glint);
      u.uDisplay.value = toCanvas(r); this.pointMaterial.uniformsNeedUpdate = true;
    };
    this.object.add(this.points);
    if (belt && o.dust > 0) {
      const lanes = new Uint8Array(256 * 4);
      for (let i = 0; i < 256; i++) lanes.set([Math.round(255 * beltDensity((i + 0.5) / 256, this.lanes)), 0, 0, 255], i * 4);
      u.uLanes.value = new THREE.DataTexture(lanes, 256, 1, THREE.RGBAFormat); u.uLanes.value.magFilter = u.uLanes.value.minFilter = THREE.LinearFilter; u.uLanes.value.needsUpdate = true;
      const ring = new THREE.RingGeometry(o.inner, o.outer, 160, 1); ring.rotateX(-Math.PI / 2);
      this.dustMaterial = new THREE.ShaderMaterial({...common, side: THREE.DoubleSide, vertexShader: "varying vec3 vAt; void main() { vAt = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }", fragmentShader: BELT_DUST_FRAG});
      this.dust = new THREE.Mesh(ring, this.dustMaterial); this.dust.renderOrder = -1;
      this.dust.onBeforeRender = (r) => { u.uDisplay.value = toCanvas(r); this.dustMaterial.uniformsNeedUpdate = true; };
      this.object.add(this.dust);
    }
    this.shown = 0;
    this._m = new THREE.Matrix4(); this._q = new THREE.Quaternion(); this._v = new THREE.Vector3(); this._s = new THREE.Vector3(); this._c = new THREE.Color(); this._eye = new THREE.Vector3(); this._axis = new THREE.Vector3();
  }
  /** Where rock `i` is at time t in the object's own axes: [x, y, z, shown (0..1)]. `eye`: the camera there (a field that follows it). */
  place(i, t, eye = null, out = [0, 0, 0, 1]) {
    const o = this.options, b = this.base, k = i * 4;
    if (this.belt) {
      // a slightly oval orbit in a slightly tilted plane, faster nearer the middle (Kepler's third law)
      const a = b[k], angle = b[k + 1] + o.rate * t * Math.pow(a / o.inner, -1.5), node = b[k + 3], r = a * (1 - o.eccentricity * Math.cos(angle - node * 1.7));
      out[0] = r * Math.cos(angle); out[2] = r * Math.sin(angle); out[1] = r * Math.tan(b[k + 2]) * Math.sin(angle - node); out[3] = 1;
      return out;
    }
    let shown = 1;
    for (let j = 0; j < 3; j++) {
      let x = b[k + j];
      if (o.follow && eye) {
        // the box repeats round the camera: a rock shrinks to nothing where it would jump to the other side
        const e = j === 0 ? eye.x : j === 1 ? eye.y : eye.z, d = x - e, w = d - o.size * Math.round(d / o.size);
        x = e + w; shown *= 1 - smooth(0.4, 0.5, Math.abs(w) / o.size);
      }
      out[j] = x;
    }
    out[3] = shown;
    return out;
  }
  /** Set the rocks to time t for `camera` (needed: which rocks are meshes depends on their size in the picture).
   * `sun`: the direction to the sun for the far points ([x, y, z], or "centre": the star stands in the belt's middle;
   * default the `light` option's, a spaceLight, else the `sun` option). */
  update(t, {camera = null, sun = null} = {}) {
    if (!camera) throw fail("asteroids.update(t, {camera}): give the camera (the near rocks are chosen by their size in the picture)");
    const o = this.options, u = this.uniforms, n = this.count, light = o.light && o.light.directional ? o.light.directional : null;
    u.uRocks.value.y = (sun ?? (light ? null : o.sun)) === "centre" ? 1 : 0;
    if (u.uRocks.value.y) u.uSun.value.set(0, 1, 0);
    else if (sun) u.uSun.value.set(...vector("asteroids.update: sun", sun));
    else if (light) u.uSun.value.copy(light.position).sub(light.target.position);
    else u.uSun.value.set(...vector("asteroids: sun", o.sun));
    if (light) u.uSunColor.value.set(light.color.r, light.color.g, light.color.b).multiplyScalar(light.intensity / Math.PI); else u.uSunColor.value.set(1, 1, 1);
    u.uDust.value.z = 0.05 * o.dust * o.brightness;
    this.object.updateWorldMatrix(true, false); camera.updateWorldMatrix(true, false);
    const eye = this.object.worldToLocal(camera.getWorldPosition(this._eye)), scale = this.object.matrixWorld.getMaxScaleOnAxis();
    const height = this.renderer.getDrawingBufferSize(new THREE.Vector2()).y, focal = height / (2 * Math.tan((camera.fov ?? 40) * Math.PI / 360));
    for (const lods of this.meshes) for (const m of lods) m.count = 0;
    const at = [0, 0, 0, 1], P = this.positions, L = this.look, T = this.turn;
    let shown = 0;
    for (let i = 0; i < n; i++) {
      this.place(i, t, eye, at);
      P[i * 3] = at[0]; P[i * 3 + 1] = at[1]; P[i * 3 + 2] = at[2]; L[i * 4 + 1] = at[3];
      const r = this.radius[i], dist = Math.hypot(at[0] - eye.x, at[1] - eye.y, at[2] - eye.z), px = (r * focal) / Math.max(dist, 1e-9);
      if (px <= ROCK_LODS[2].over || at[3] <= 0) continue;
      const lods = this.meshes[this.shapeOf[i]];
      let k = px > ROCK_LODS[0].over ? 0 : px > ROCK_LODS[1].over ? 1 : 2;
      while (k < 2 && lods[k].count >= lods[k].instanceMatrix.count) k++;
      const mesh = lods[k];
      if (mesh.count >= mesh.instanceMatrix.count) continue;
      this._q.setFromAxisAngle(this._axis.set(T[i * 5], T[i * 5 + 1], T[i * 5 + 2]), T[i * 5 + 3] + T[i * 5 + 4] * t);
      // (as a mesh it grows in over the sizes where its point fades out)
      const grow = r * at[3] * smooth(ROCK_LODS[2].over, 2.6, px);
      this._m.compose(this._v.set(at[0], at[1], at[2]), this._q, this._s.set(grow, grow, grow));
      mesh.setMatrixAt(mesh.count, this._m); mesh.setColorAt(mesh.count, this._c.setRGB(this.tints[i * 3], this.tints[i * 3 + 1], this.tints[i * 3 + 2]));
      mesh.count++; shown++;
    }
    for (const lods of this.meshes) for (const m of lods) { m.instanceMatrix.needsUpdate = true; m.instanceColor.needsUpdate = true; m.visible = m.count > 0; }
    this.geometry.getAttribute("position").needsUpdate = true; this.geometry.getAttribute("aRock").needsUpdate = true;
    this.shown = shown; this._scale = scale;
    return this;
  }
  dispose() {
    this.object.removeFromParent(); this.geometry.dispose(); this.pointMaterial.dispose(); this.material.dispose();
    for (const lods of this.meshes) for (const m of lods) { m.geometry.dispose(); m.dispose(); }
    if (this.dust) { this.dust.geometry.dispose(); this.dustMaterial.dispose(); this.uniforms.uLanes.value.dispose(); }
  }
}
/** Rocks by the thousand: `asteroids(renderer, {layout: "field" | "belt", seed, count, size, least, most, power, shapes,
 * rocks, follow, tumble, glint, color, variety, albedo, brightness, dust, inner, outer, thickness, rate, gaps, eccentricity, light, sun, quality})`; DESIGN.md §122.9. */
export const asteroids = (renderer, options = {}) => new Asteroids(renderer, options);

// ====================================================================================================
// Comet
// ====================================================================================================
export const COMET_DEFAULTS = Object.freeze({seed: 1, nucleus: 0.012, coma: 1, dust: 1, ion: 1, jets: 3, length: 30, ionLength: 52, curve: 0.34, activity: 1,
  dustColor: 0xfff0d0, ionColor: 0x74a9ff, comaColor: 0xc9ffe6, spin: 9, space: null, body: null, orbits: null, unit: 2e9, reference: 1.496e11, quality: "normal"});
/** How active a comet is at `distance` from its star (the same unit as `reference`, the distance of activity
 * 1; default 1 AU in metres): the gas a sunlit ice gives off grows about as 1 / distance^2; under a tenth
 * (past about three times the reference) nothing shows, and it is held at 1.6. */
export function cometActivity(distance, reference = 1.496e11) { const a = Math.pow(reference / Math.max(distance, 1e-9), 2); return a < 0.1 ? 0 : Math.min(1.6, a); }
/** The directions of a comet's tails from the sun's direction and the comet's velocity (any lengths): {away
 * (unit: from the sun; the ion tail's line), lag (unit, square to `away`, against the motion: the side the dust tail bends to)}. */
export function cometFrame(toSun, velocity) {
  const away = unit([-toSun[0], -toSun[1], -toSun[2]]), along = dot(velocity, away);
  let lag = [-(velocity[0] - along * away[0]), -(velocity[1] - along * away[1]), -(velocity[2] - along * away[2])];
  if (Math.hypot(lag[0], lag[1], lag[2]) < 1e-9) lag = cross(away, Math.abs(away[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0]);
  return {away, lag: unit(lag)};
}
// a ribbon along a curve from the nucleus that always faces the camera: its shape is worked out in the vertex shader
const TAIL_VERT = /* glsl */`
attribute vec2 aAt;      // along (0..1), across (-1..1)
uniform vec3 uAway, uLag, uFrom;
uniform vec4 uShape;     // length, bend, width at the head, width at the end
uniform vec4 uLook;      // light, time, kind, activity
varying vec3 vUV; varying float vNear;
void main() {
  float s = aAt.x, len = uShape.x;
  vec3 at = uFrom + len * (s * uAway + uShape.y * pow(s, 1.7) * uLag);
  vec3 tangent = normalize(uAway + uShape.y * 1.7 * pow(max(s, 1e-3), 0.7) * uLag);
  vec4 world = modelMatrix * vec4(at, 1.0);
  vec3 tw = normalize(mat3(modelMatrix) * tangent), view = normalize(cameraPosition - world.xyz), side = cross(tw, view);
  float edge = length(side); side /= max(edge, 1e-4);
  float width = len * mix(uShape.z, uShape.w, pow(s, 0.8)) * length(modelMatrix[0].xyz);
  world.xyz += side * aAt.y * width;
  // which way the dust lags, as the ribbon sees it: its sharp edge leads
  vUV = vec3(s, aAt.y * sign(dot(side, mat3(modelMatrix) * uLag) + 1e-6), smoothstep(0.03, 0.25, edge));
  // seen from inside the head the tails are thin haze all round: they fade as the camera comes close (jets do not)
  vNear = uLook.z > 1.5 ? 1.0 : max(pow(clamp(length(cameraPosition - modelMatrix[3].xyz) / (12.0 * length(modelMatrix[0].xyz)), 0.0, 1.0), 1.5), 0.004);
  gl_Position = projectionMatrix * viewMatrix * world;
}`;
const TAIL_FRAG = /* glsl */`
uniform sampler2D uNoise; uniform vec4 uLook; uniform vec3 uColor;
varying vec3 vUV; varying float vNear;
${DISPLAY}
void main() {
  float s = vUV.x, w = vUV.y, light;
  vec3 col = uColor;
  if (uLook.z < 0.5) {
    // dust: a broad fan, sharp on the leading edge and soft on the lagging one, with faint bands across it
    float lead = w < 0.0 ? exp(-w * w / 0.10) : exp(-w * w / 0.34), fall = pow(1.0 - s, 1.6) * exp(-1.2 * s) * smoothstep(0.0, 0.03, s);
    float bands = texture2D(uNoise, vec2(s * 1.1 + w * 0.35 - uLook.y * 0.004, w * 0.2 + 0.2)).r, grain = texture2D(uNoise, vec2(s * 0.35 - uLook.y * 0.006, w * 0.45)).g;
    light = lead * fall * (0.6 + 0.6 * bands) * (0.75 + 0.45 * grain) * (1.0 - smoothstep(0.75, 1.0, abs(w)));
    col = mix(uColor, uColor * vec3(1.0, 0.82, 0.62), s);
  } else if (uLook.z < 1.5) {
    // ions: thin straight rays that fan out a little, with knots that drift away from the sun
    float fall = pow(1.0 - s, 1.1) * exp(-1.1 * s) * smoothstep(0.0, 0.02, s), rays = 0.0;
    for (int k = 0; k < 5; k++) {
      float fk = float(k), off = (fk - 2.0) * 0.33 + 0.12 * sin(fk * 5.1 + s * 6.0 + uLook.y * 0.05), wide = 0.05 + 0.05 * fract(fk * 0.37 + 0.2);
      rays += (0.45 + 0.55 * fract(fk * 0.618 + 0.3)) * exp(-(w - off * smoothstep(0.0, 0.5, s)) * (w - off * smoothstep(0.0, 0.5, s)) / (wide * wide));
    }
    float knots = texture2D(uNoise, vec2(s * 3.0 - uLook.y * 0.03, w * 0.4 + 0.6)).r;
    light = fall * (0.34 * exp(-w * w / 0.3) + 0.6 * rays) * (0.5 + 1.0 * knots * knots) * (1.0 - smoothstep(0.8, 1.0, abs(w)));
  } else {
    // a jet: a narrow bright fan from the ground
    light = pow(1.0 - s, 1.6) * exp(-w * w / 0.16) * (0.7 + 0.5 * texture2D(uNoise, vec2(s * 1.5 - uLook.y * 0.05, w * 0.5)).g) * (1.0 - smoothstep(0.8, 1.0, abs(w)));
  }
  gl_FragColor = vec4(display(col * light * uLook.x * vNear * vUV.z), 1.0);
}`;
const COMA_VERT = /* glsl */`
uniform vec4 uComa;   // radius, light, 0, 0
uniform vec3 uAway;
varying vec2 vP; varying vec2 vAway; varying float vNear;
void main() {
  vec4 centre = modelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0);
  float r = uComa.x * length(modelMatrix[0].xyz);
  vP = position.xy * 4.0;
  // from inside the head its glow is all round the camera and thin: it fades as the camera comes close
  vNear = max(pow(clamp(length(centre.xyz) / (6.0 * r), 0.0, 1.0), 1.5), 0.012);
  vec3 a = mat3(viewMatrix) * (mat3(modelMatrix) * uAway);
  vAway = length(a.xy) > 1e-4 ? normalize(a.xy) * (0.35 + 0.65 * length(a.xy) / length(a)) : vec2(0.0);
  gl_Position = projectionMatrix * (centre + vec4(position.xy * 4.0 * r, 0.0, 0.0));
}`;
const COMA_FRAG = /* glsl */`
uniform vec4 uComa; uniform vec3 uColor, uDust;
varying vec2 vP; varying vec2 vAway; varying float vNear;
${DISPLAY}
void main() {
  // the head: gas streaming off the nucleus and swept back, so it is tight on the sunward side and long behind
  float along = dot(vP, vAway), across = length(vP - along * vAway / max(dot(vAway, vAway), 1e-4) * dot(vAway, vAway));
  float k = along < 0.0 ? 1.0 + 1.1 * length(vAway) : 1.0 - 0.45 * length(vAway);
  float r = sqrt(across * across + along * along * k * k), r1 = length(vP);
  float core = 1.0 / (1.0 + pow(r / 0.07, 2.0)), halo = exp(-r * 1.7) * 0.22, cut = 1.0 - smoothstep(2.6, 4.0, r1);
  // a faint shell where the outflow meets the sun's wind
  float shell = 0.035 * exp(-pow((r - 1.15) / 0.16, 2.0)) * smoothstep(0.2, -0.6, along / max(r1, 1e-3));
  vec3 col = mix(uDust, uColor, smoothstep(0.02, 0.5, r)) * (core * 1.6 + halo + shell) * cut * uComa.y * vNear;
  gl_FragColor = vec4(display(col), 1.0);
}`;

/** A comet: a dark nucleus with jets, a head of gas, a curved dust tail and a straight ion tail. `object` (add
 * it to the scene; one unit = the head's size: scale it), `update(t, {sun, velocity, activity})`, `nucleus`
 * (its `object` hides the glare of a vidgen/space-light star), `state`, `dispose()`. */
export class Comet {
  constructor(renderer, options = {}) {
    needRenderer("comet(renderer, options)", renderer);
    const o = this.options = resolve("comet", options, COMET_DEFAULTS);
    choice("comet: quality", o.quality, QUALITIES);
    for (const k of ["coma", "dust", "ion"]) number(`comet: ${k}`, o[k], 0, 16);
    number("comet: nucleus", o.nucleus, 1e-6, 1); number("comet: jets", o.jets, 0, 6); number("comet: length", o.length, 0.1, 1e4); number("comet: ionLength", o.ionLength, 0.1, 1e4); number("comet: curve", o.curve, 0, 1.5);
    this.renderer = renderer;
    this.object = new THREE.Group(); this.object.name = "comet";
    const color = (c) => new THREE.Vector3(...new THREE.Color(c).toArray()), noise = this._noise = noiseTexture(o.seed + 5);
    const shared = {uAway: {value: new THREE.Vector3(1, 0, 0)}, uLag: {value: new THREE.Vector3(0, 0, 1)}, uNoise: {value: noise}, uDisplay: {value: 0}};
    const common = {blending: THREE.AdditiveBlending, transparent: true, depthTest: true, depthWrite: false, toneMapped: false, fog: false, side: THREE.DoubleSide};
    const reach = Math.max(o.length, o.ionLength) * 1.2;
    const strip = (segments) => {
      const at = new Float32Array((segments + 1) * 4), index = [];
      for (let i = 0; i <= segments; i++) { at.set([i / segments, -1, i / segments, 1], i * 4); if (i < segments) index.push(i * 2, i * 2 + 1, i * 2 + 2, i * 2 + 1, i * 2 + 3, i * 2 + 2); }
      const g = new THREE.BufferGeometry(); g.setAttribute("aAt", new THREE.BufferAttribute(at, 2)); g.setAttribute("position", new THREE.BufferAttribute(new Float32Array((segments + 1) * 6), 3));
      g.setIndex(index); g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), reach);
      return g;
    };
    this._strip = strip(o.quality === "fast" ? 32 : 64);
    const tail = (kind, col, order) => {
      const uniforms = {...shared, ...(kind === 2 ? {uAway: {value: new THREE.Vector3(1, 0, 0)}, uLag: {value: new THREE.Vector3(0, 0, 1)}} : {}), uFrom: {value: new THREE.Vector3()}, uShape: {value: new THREE.Vector4()}, uLook: {value: new THREE.Vector4(0, 0, kind, 1)}, uColor: {value: color(col)}};
      const material = new THREE.ShaderMaterial({...common, uniforms, vertexShader: TAIL_VERT, fragmentShader: TAIL_FRAG});
      const mesh = new THREE.Mesh(this._strip, material); mesh.renderOrder = order;
      mesh.onBeforeRender = (r) => { shared.uDisplay.value = toCanvas(r); material.uniformsNeedUpdate = true; };
      this.object.add(mesh);
      return mesh;
    };
    this.shared = shared;
    this.dust = tail(0, o.dustColor, 1); this.ion = tail(1, o.ionColor, 2);
    this.jets = [];
    const random = rng(o.seed + 3);
    // (twice as many spots as jets seen at once: about half of them are on the night side)
    for (let i = 0; i < Math.round(o.jets) * 2; i++) { const j = tail(2, 0xffffff, 4); j.userData.jet = {dir: seededUnit(random), length: 0.5 + 0.6 * random(), width: 0.1 + 0.12 * random()}; this.jets.push(j); }
    const comaUniforms = {...shared, uComa: {value: new THREE.Vector4(1, 1, 0, 0)}, uColor: {value: color(o.comaColor)}, uDust: {value: color(0xfff3dc)}};
    this.comaMaterial = new THREE.ShaderMaterial({...common, uniforms: comaUniforms, vertexShader: COMA_VERT, fragmentShader: COMA_FRAG});
    const quad = new THREE.PlaneGeometry(2, 2); quad.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 12);
    this.coma = new THREE.Mesh(quad, this.comaMaterial); this.coma.renderOrder = 3;
    this.coma.onBeforeRender = (r) => { shared.uDisplay.value = toCanvas(r); this.comaMaterial.uniformsNeedUpdate = true; };
    this.object.add(this.coma);
    // the nucleus: a small, very dark rock that turns
    this.nucleus = new Asteroid({seed: o.seed + 11, detail: o.quality === "fine" ? 40 : 20, craters: 12, color: 0x2a2724, spin: o.spin});
    this.nucleus.object.scale.setScalar(o.nucleus); this.object.add(this.nucleus.object);
    // ctx.orbits: the comet's place, the sun's direction, its motion and its activity
    this.space = o.space; this.orbits = o.orbits ?? (o.space ? o.space.orbits : null); this.body = null;
    if (this.orbits) {
      const want = String(o.body ?? "").toLowerCase();
      this.body = this.orbits.names.find((n) => n.toLowerCase() === want) ?? this.orbits.names.find((n) => (this.orbits.bodies[n].key ?? "").toLowerCase() === want) ?? null;
      if (!this.body) throw fail(`comet: the orbit data has no body "${o.body ?? ""}"${hint(want, this.orbits.names)}; it has: ${this.orbits.names.join(", ")} (give {body: name})`);
      this.sunBody = this.orbits.names.find((n) => this.orbits.bodies[n].key === "sun") ?? this.orbits.central ?? this.orbits.names[0];
      // (a comet's head and tails are far larger than its nucleus and far smaller than its orbit: `unit` metres per unit is a stated size)
      if (this.space) this.space.add(this.object, {body: this.body, size: number("comet: unit", o.unit, 1e-3, 1e15), spin: false});
    } else if (o.body !== null || o.space) throw fail("comet: space / body need orbit data: a web scene with orbit_data: (ctx.orbits)");
    /** After update(): {activity, away, lag, distance (from the sun, with orbit data)}. */
    this.state = {activity: o.activity, away: [1, 0, 0], lag: [0, 0, 1], distance: null};
    this.update(0);
  }
  /** Set the comet to time t. `sun`: the direction to the sun ([x, y, z]), `velocity`: its motion (any length;
   * the dust tail lags behind it), `activity` (0..1.6: how far the tails and the head have grown). With orbit
   * data all three come from the data (the tails grow as the comet nears the sun) unless given. */
  update(t, {sun = null, velocity = null, activity = null} = {}) {
    const o = this.options;
    let toSun = sun ? vector("comet.update: sun", sun) : this._sun ?? [-1, 0, 0], motion = velocity ? vector("comet.update: velocity", velocity) : this._velocity ?? [0, 0, 1], act = activity ?? this._activity ?? o.activity, distance = null;
    if (this.orbits && this.body) {
      // the data's axes (z up) become three's (y up) as vidgen/space-scale turns them
      const up = (v) => [v[0], v[2], -v[1]], p = this.orbits.position(this.body, t), s = this.orbits.position(this.sunBody, t), v = this.orbits.velocity(this.body, t), sv = this.orbits.velocity(this.sunBody, t);
      const rel = [s[0] - p[0], s[1] - p[1], s[2] - p[2]];
      distance = Math.hypot(rel[0], rel[1], rel[2]);
      if (!sun) toSun = up(rel);
      if (!velocity) motion = up([v[0] - sv[0], v[1] - sv[1], v[2] - sv[2]]);
      if (activity === null) act = cometActivity(distance, o.reference) * o.activity;
    }
    if (sun) this._sun = toSun; if (velocity) this._velocity = motion; if (activity !== null) this._activity = act;
    number("comet.update: activity", act, 0, 1.6);
    // into the comet's own axes (it may be turned or sit in a turned parent)
    this.object.updateWorldMatrix(true, false);
    const inverse = new THREE.Matrix3().setFromMatrix4(this.object.matrixWorld).invert(), local = (v) => new THREE.Vector3(...v).applyMatrix3(inverse).toArray();
    const frame = cometFrame(local(toSun), local(motion)), grow = Math.sqrt(act), sh = this.shared;
    sh.uAway.value.set(...frame.away); sh.uLag.value.set(...frame.lag);
    const set = (mesh, length, bend, w0, w1, light) => { const u = mesh.material.uniforms; u.uShape.value.set(length, bend, w0, w1); u.uLook.value.set(light, t, u.uLook.value.z, act); mesh.visible = light > 1e-4; };
    set(this.dust, o.length * grow, o.curve, 0.015, 0.3, 1.0 * o.dust * act);
    set(this.ion, o.ionLength * grow, 0, 0.008, 0.07, 0.42 * o.ion * act * smooth(0.15, 0.6, act));
    // jets: from spots that turn with the nucleus, lit only while they face the sun, bent back by the outflow
    const spin = this.nucleus.update(t).object.quaternion, sunward = new THREE.Vector3(...frame.away).negate();
    for (const mesh of this.jets) {
      const j = mesh.userData.jet, dir = new THREE.Vector3(...j.dir).applyQuaternion(spin), facing = smooth(0.05, 0.5, dir.dot(sunward)), u = mesh.material.uniforms;
      u.uAway.value.copy(dir); u.uLag.value.set(...frame.away); u.uFrom.value.copy(dir).multiplyScalar(o.nucleus * 0.8);
      set(mesh, o.nucleus * 18 * j.length * grow, 0.22, j.width * 0.2, j.width * 0.8, 0.55 * facing * act);
    }
    const cu = this.comaMaterial.uniforms; cu.uComa.value.set(1.1 + 0.9 * grow, 1.4 * o.coma * Math.min(act, 1.2), 0, 0); this.coma.visible = act > 1e-4;
    this.state = {activity: act, away: frame.away, lag: frame.lag, distance};
    return this;
  }
  dispose() {
    this.object.removeFromParent(); this._strip.dispose(); this._noise.dispose(); this.nucleus.dispose(); this.coma.geometry.dispose(); this.comaMaterial.dispose();
    for (const m of [this.dust, this.ion, ...this.jets]) m.material.dispose();
  }
}
/** A comet: `comet(renderer, {seed, nucleus, coma, dust, ion, jets, length, ionLength, curve, activity, dustColor,
 * ionColor, comaColor, spin, space, body, orbits, unit, reference, quality})`; DESIGN.md §122.9. */
export const comet = (renderer, options = {}) => new Comet(renderer, options);

// ====================================================================================================
// Aurora
// ====================================================================================================
export const AURORA_DEFAULTS = Object.freeze({seed: 1, latitude: 68, width: 1.2, offset: 9, height: 1, brightness: 1, speed: 1, color: 0x4dff8a, top: 0xff3d6e, poles: "both", day: 0.12});
const AURORA_SHELLS = Object.freeze([{h: 0.016, top: 0.0, gain: 1.0, wide: 1.0}, {h: 0.026, top: 0.25, gain: 0.7, wide: 1.1}, {h: 0.038, top: 0.7, gain: 0.42, wide: 1.25}, {h: 0.052, top: 1.0, gain: 0.25, wide: 1.45}]);
const AURORA_VERT = /* glsl */`
varying vec3 vLocal, vWorldNormal, vWorld;
void main() {
  vLocal = normalize(position);
  vec4 world = modelMatrix * vec4(position, 1.0);
  vWorld = world.xyz; vWorldNormal = normalize(mat3(modelMatrix) * vLocal);
  gl_Position = projectionMatrix * viewMatrix * world;
}`;
const AURORA_FRAG = /* glsl */`
uniform sampler2D uNoise; uniform vec3 uSun, uColor, uTop;
uniform vec4 uOval;    // the oval's colatitude (radians), its width, time, light
uniform vec4 uShell;   // how far up (0 green foot .. 1 red top), gain, widening, the day side's share
varying vec3 vLocal, vWorldNormal, vWorld;
${DISPLAY}
void main() {
  // angles round the magnetic pole: the strip's own axis (it is turned to stand off the pole of turning)
  float colat = acos(clamp(vLocal.y, -1.0, 1.0)), lon = atan(vLocal.z, vLocal.x) / 6.2831853;
  // curtains: the oval wanders, breaks into folds and rays that drift
  float wander = texture2D(uNoise, vec2(lon * 2.0 + uOval.z * 0.004, 0.31)).r - 0.5, fold = texture2D(uNoise, vec2(lon * 5.0 - uOval.z * 0.011, 0.62 + uOval.z * 0.002)).g;
  float rays = texture2D(uNoise, vec2(lon * 41.0 + uOval.z * 0.02, 0.17 + uShell.x * 0.05)).r, arc = (colat - uOval.x - wander * 0.09) / (uOval.y * uShell.z);
  float band = exp(-arc * arc) * (0.3 + 0.7 * smoothstep(0.25, 0.7, fold)) + 0.35 * exp(-pow((arc + 1.8) / 0.7, 2.0)) * smoothstep(0.45, 0.8, rays);
  float light = band * (0.3 + 1.2 * rays * rays);
  // on the night side (a little on the day side too, where the sky's own light hides it)
  float night = mix(uShell.w, 1.0, smoothstep(0.12, -0.25, dot(normalize(vWorldNormal), normalize(uSun))));
  // a thin glowing sheet is brighter where the eye looks along it: at the limb
  float along = 1.0 / max(abs(dot(normalize(vWorldNormal), normalize(cameraPosition - vWorld))), 0.22);
  vec3 col = mix(uColor, uTop, uShell.x) * light * night * along * uShell.y * uOval.w * 0.3;
  gl_FragColor = vec4(display(col), 1.0);
}`;
/** The lights round a world's magnetic poles: curtains on an oval, green below and red above, bright on the
 * night side. `object` (it is added to the body and turns with its ground), `update(t)`, `dispose()`.
 * `body`: a world of vidgen/space-bodies (its `spinner`, `sun`), or any object of radius 1 with {sun} given to update. */
export class Aurora {
  constructor(body, options = {}) {
    const o = this.options = resolve("aurora", options, AURORA_DEFAULTS);
    number("aurora: latitude", o.latitude, 30, 89); number("aurora: width", o.width, 0.2, 20); number("aurora: offset", o.offset, 0, 40); number("aurora: height", o.height, 0.1, 20);
    number("aurora: brightness", o.brightness, 0, 64); number("aurora: day", o.day, 0, 1); choice("aurora: poles", o.poles, ["both", "north", "south"]);
    this.body = body;
    const parent = body && body.spinner ? body.spinner : body && body.object ? body.object : body;
    if (!parent || !parent.isObject3D) throw fail("aurora(body, options): the first argument must be a world of vidgen/space-bodies or a THREE.Object3D of radius 1");
    this.object = new THREE.Group(); this.object.name = "aurora";
    const noise = this._noise = noiseTexture(o.seed + 23), random = rng(o.seed), turn = random() * TAU, colat = (90 - o.latitude) * Math.PI / 180, off = o.offset * Math.PI / 180;
    const color = (c) => new THREE.Vector3(...new THREE.Color(c).toArray());
    this.materials = [];
    this.sun = new THREE.Vector3(1, 0, 0);
    // a strip of a sphere round the magnetic pole, just wide enough for the wandering oval and its widest shell
    const half = (2.5 + o.width * 4.5) * Math.PI / 180 + 0.09, from = Math.max(0.01, colat - half), up = new THREE.Vector3(0, 1, 0);
    for (const sign of o.poles === "both" ? [1, -1] : o.poles === "north" ? [1] : [-1]) {
      const pole = new THREE.Vector3(Math.sin(off) * Math.cos(turn), sign * Math.cos(off), Math.sin(off) * Math.sin(turn) * sign).normalize();
      AURORA_SHELLS.forEach((shell, k) => {
        const geometry = new THREE.SphereGeometry(1 + shell.h * o.height, 128, 8, 0, TAU, from, Math.min(colat + half, Math.PI - 0.01) - from);
        const uniforms = {uNoise: {value: noise}, uSun: {value: this.sun}, uColor: {value: color(o.color)}, uTop: {value: color(o.top)},
          uOval: {value: new THREE.Vector4(colat, o.width * Math.PI / 180, 0, o.brightness)}, uShell: {value: new THREE.Vector4(shell.top, shell.gain, shell.wide, o.day)}, uDisplay: {value: 0}};
        const material = new THREE.ShaderMaterial({uniforms, vertexShader: AURORA_VERT, fragmentShader: AURORA_FRAG, blending: THREE.AdditiveBlending, transparent: true, depthTest: true, depthWrite: false, toneMapped: false, fog: false, side: THREE.DoubleSide});
        const mesh = new THREE.Mesh(geometry, material); mesh.renderOrder = 5 + k; mesh.quaternion.setFromUnitVectors(up, pole);
        mesh.onBeforeRender = (r) => { uniforms.uDisplay.value = toCanvas(r); material.uniformsNeedUpdate = true; };
        this.object.add(mesh); this.materials.push(material);
      });
    }
    parent.add(this.object);
    this.update(0);
  }
  /** Set the curtains to time t. `sun`: the direction to the sun in the world ([x, y, z]; default the body's own, `body.sun`). */
  update(t, {sun = null} = {}) {
    const s = sun ?? (this.body && this.body.sun ? this.body.sun : null);
    if (s) this.sun.set(...vector("aurora.update: sun", s.direction ?? s));
    for (const m of this.materials) m.uniforms.uOval.value.z = t * this.options.speed * 10;
    return this;
  }
  dispose() { this.object.removeFromParent(); this._noise.dispose(); for (const m of this.object.children) { m.geometry.dispose(); m.material.dispose(); } }
}
/** An aurora on a world: `aurora(body, {seed, latitude, width, offset, height, brightness, speed, color, top, poles, day})`; DESIGN.md §122.9. */
export const aurora = (body, options = {}) => new Aurora(body, options);
