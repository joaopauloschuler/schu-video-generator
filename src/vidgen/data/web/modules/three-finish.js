// vidgen/three-finish: ready-made finishing for three.js `web` scenes (DESIGN.md §120.11; the sensor: §124.1).
// Part of schu-video-generator (MIT licence); imported by a page as "vidgen/three-finish".
//
//   const finish = new Finish(renderer, scene, camera, ctx, {update: (t) => {...}, dof: {...}, ...});
//   finish.warmUp(0);          // in load (optional): shaders compiled before frame 0
//   finish.render(t);          // in frame(t, ctx), instead of renderer.render
//
// The chain: the scene (at `renderScale`; `motionBlur` draws it `samples` times across the shutter
// by calling `update` at sub-frame times and averages them) -> depth of field from the depth buffer
// -> bloom on the highlights (linear values above `threshold`) -> chromatic fringe, exposure, white
// balance, vignette -> tone mapping -> saturation -> sRGB encoding (once) -> contrast, lift, gamma,
// gain -> FXAA -> film grain seeded by the frame number. Off by default, a camera's sensor (Step 397): a
// limited dynamic range right after tone mapping (`range`: highlights clip with a short shoulder, shadows
// crush), in-camera sharpening after FXAA (`sharpen`: faint halos) and sensor noise in place of the grain
// (`noise`: signal-dependent, coloured, at the sensor's scale). Everything is a function of `t` and the
// options, so two renders of a frame are the same. Intermediate pictures are linear half floats;
// the scene's own render targets get no tone mapping or colour-space conversion from three.js.
import * as THREE from "three";
import {FullScreenQuad} from "three/addons/postprocessing/Pass.js";
import {UnrealBloomPass} from "three/addons/postprocessing/UnrealBloomPass.js";

export const VERSION = 1;

const PREFIX = "vidgen/three-finish";
const TONE_MAPPINGS = ["aces", "agx", "neutral", "aces-narkowicz", "none"];
const ANTIALIAS = ["fxaa", "none"];
const ENCODINGS = ["srgb", "gamma2.2"];
const QUALITY = {low: {taps: 12, half: true}, medium: {taps: 20, half: true}, high: {taps: 32, half: false}};
const DEFAULTS = {
  update: null, renderScale: 1, toneMapping: "aces", encoding: "srgb", exposure: 1, fade: 1, grain: 0.02, fringe: 0, antialias: "fxaa",
  bloom: {strength: 0.25, radius: 0.2, threshold: 1, scale: 0.5},
  grade: {temperature: 0, tint: 0, saturation: 1, contrast: 1, lift: 0, gamma: 1, gain: 1, filter: 1},
  vignette: {amount: 0.3, inner: 0.3, outer: 1.2},
  flash: {amount: 0, color: 1},
  noise: {amount: 0, color: 0.5, size: 1, floor: 0.05},
  range: {stops: 0, shoulder: 0.05, black: 0},
  sharpen: {amount: 0, radius: 1, limit: 0.06},
  dof: false, motionBlur: false,
};
// the camera's sensor (Step 397): off by default; `true`, a number or an object turns it on with these
const SENSOR_ON = {noise: 0.012, range: 2.5, sharpen: 0.5};
const DOF_DEFAULTS = {focus: 10, fStop: 2.8, unit: 1, blur: null, maxBlur: 10, quality: "medium"};
const MOTION_DEFAULTS = {samples: 5, shutter: 180};
// options that take a sub-object (true = its defaults; false = off where allowed)
const GROUPS = {bloom: DEFAULTS.bloom, grade: DEFAULTS.grade, vignette: DEFAULTS.vignette, flash: DEFAULTS.flash, dof: DOF_DEFAULTS, motionBlur: MOTION_DEFAULTS,
  noise: DEFAULTS.noise, range: DEFAULTS.range, sharpen: DEFAULTS.sharpen};
const SCALAR_GROUP = {vignette: "amount", flash: "amount", bloom: "strength", noise: "amount", range: "stops", sharpen: "amount"};

// ---------- options ----------
function distance(a, b) {
  const d = Array.from({length: b.length + 1}, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = d[0]; d[0] = i;
    for (let j = 1; j <= b.length; j++) { const cur = d[j]; d[j] = Math.min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = cur; }
  }
  return d[b.length];
}
function unknown(where, key, known) {
  const best = known.map((k) => [distance(key.toLowerCase(), k.toLowerCase()), k]).sort((x, y) => x[0] - y[0])[0];
  const hint = best && best[0] <= Math.max(2, key.length / 3) ? ` (did you mean "${best[1]}"?)` : "";
  return new Error(`${PREFIX}: unknown option ${where}"${key}"${hint}; known: ${known.join(", ")}`);
}
const fail = (msg) => new Error(`${PREFIX}: ${msg}`);
function number(where, v, lo, hi) {
  if (typeof v !== "number" || !Number.isFinite(v) || v < lo || v > hi) throw fail(`${where} must be a number from ${lo} to ${hi}, got ${JSON.stringify(v)}`);
  return v;
}
function choice(where, v, list) {
  if (!list.includes(v)) throw fail(`${where} must be one of ${list.map((x) => JSON.stringify(x)).join(", ")}, got ${JSON.stringify(v)}`);
  return v;
}
// a colour or a per-channel factor: a number (all three channels), [r, g, b], a THREE.Color or a CSS colour (linear)
function triple(where, v) {
  if (typeof v === "number" && Number.isFinite(v)) return [v, v, v];
  if (Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === "number" && Number.isFinite(x))) return v.slice();
  if (v && v.isColor) return [v.r, v.g, v.b];
  if (typeof v === "string") { const c = new THREE.Color(v); return [c.r, c.g, c.b]; }
  throw fail(`${where} must be a number, [r, g, b], a THREE.Color or a colour string, got ${JSON.stringify(v)}`);
}
function group(name, value) {
  const defaults = GROUPS[name];
  if (name in SENSOR_ON) {   // not given: off; given (true or an object): on at SENSOR_ON unless it says otherwise
    if (value === true) value = {};
    if (value && typeof value === "object" && !Array.isArray(value)) value = {[SCALAR_GROUP[name]]: SENSOR_ON[name], ...value};
  }
  if (value === false || value === null) {
    if (name === "dof" || name === "motionBlur" || name === "bloom") return false;
    return {...defaults, [SCALAR_GROUP[name] ?? "amount"]: 0};
  }
  if (value === true || value === undefined) return {...defaults};
  if (typeof value === "number" && SCALAR_GROUP[name]) return {...defaults, [SCALAR_GROUP[name]]: value};
  if (typeof value !== "object" || Array.isArray(value)) throw fail(`${name} must be an object${SCALAR_GROUP[name] ? `, a number (its ${SCALAR_GROUP[name]})` : ""}, true or false, got ${JSON.stringify(value)}`);
  const known = Object.keys(defaults);
  for (const k of Object.keys(value)) if (!known.includes(k)) throw unknown(`${name}.`, k, known);
  return {...defaults, ...value};
}

/** The options in full, checked: defaults filled in, each value in range; `t` resolves values that are functions of time. */
export function resolveOptions(options = {}, t = 0) {
  if (options === null || typeof options !== "object") throw fail(`the options must be an object, got ${JSON.stringify(options)}`);
  const known = Object.keys(DEFAULTS);
  for (const k of Object.keys(options)) if (!known.includes(k)) throw unknown("", k, known);
  const at = (k) => { const v = options[k]; return typeof v === "function" && k !== "update" ? v(t) : v; };
  const part = (k) => group(k, at(k) === undefined ? (k in SENSOR_ON ? undefined : DEFAULTS[k]) : at(k));
  const o = {};
  o.update = options.update ?? null;
  if (o.update !== null && typeof o.update !== "function") throw fail(`update must be a function update(t) that sets the scene to time t, got ${typeof o.update}`);
  o.renderScale = number("renderScale", at("renderScale") ?? DEFAULTS.renderScale, 0.25, 1);
  o.toneMapping = choice("toneMapping", at("toneMapping") ?? DEFAULTS.toneMapping, TONE_MAPPINGS);
  o.encoding = choice("encoding", at("encoding") ?? DEFAULTS.encoding, ENCODINGS);
  o.exposure = number("exposure", at("exposure") ?? DEFAULTS.exposure, 0, 64);
  o.fade = number("fade", at("fade") ?? DEFAULTS.fade, 0, 1);
  o.grain = number("grain", at("grain") ?? DEFAULTS.grain, 0, 0.5);
  o.fringe = number("fringe", at("fringe") ?? DEFAULTS.fringe, 0, 10);
  o.antialias = choice("antialias", at("antialias") ?? DEFAULTS.antialias, ANTIALIAS);
  o.bloom = part("bloom");
  if (o.bloom) {
    number("bloom.strength", o.bloom.strength, 0, 10); number("bloom.radius", o.bloom.radius, 0, 1);
    number("bloom.threshold", o.bloom.threshold, 0, 100); number("bloom.scale", o.bloom.scale, 0.05, 1);
  }
  o.grade = part("grade");
  const g = o.grade;
  number("grade.temperature", g.temperature, -1, 1); number("grade.tint", g.tint, -1, 1);
  number("grade.saturation", g.saturation, 0, 4); number("grade.contrast", g.contrast, 0, 4);
  g.lift = triple("grade.lift", g.lift); g.gamma = triple("grade.gamma", g.gamma); g.gain = triple("grade.gain", g.gain); g.filter = triple("grade.filter", g.filter);
  for (const v of g.gamma) if (v <= 0) throw fail(`grade.gamma must be above 0, got ${JSON.stringify(g.gamma)}`);
  o.vignette = part("vignette");
  number("vignette.amount", o.vignette.amount, 0, 1); number("vignette.inner", o.vignette.inner, 0, 2); number("vignette.outer", o.vignette.outer, 0, 3);
  if (o.vignette.outer <= o.vignette.inner) throw fail(`vignette.outer (${o.vignette.outer}) must be larger than vignette.inner (${o.vignette.inner})`);
  o.flash = part("flash");
  number("flash.amount", o.flash.amount, 0, 100); o.flash.color = triple("flash.color", o.flash.color);
  o.noise = part("noise");
  number("noise.amount", o.noise.amount, 0, 0.5); number("noise.color", o.noise.color, 0, 1);
  number("noise.size", o.noise.size, 1, 8); number("noise.floor", o.noise.floor, 0, 0.9);
  o.range = part("range");
  if (o.range.stops !== 0) number("range.stops", o.range.stops, 1, 16);
  number("range.shoulder", o.range.shoulder, 0, 0.5); number("range.black", o.range.black, 0, 0.2);
  o.sharpen = part("sharpen");
  number("sharpen.amount", o.sharpen.amount, 0, 4); number("sharpen.radius", o.sharpen.radius, 0.5, 4); number("sharpen.limit", o.sharpen.limit, 0, 1);
  o.dof = part("dof");
  if (o.dof) {
    const d = o.dof;
    if (!(typeof d.focus === "number" || (d.focus && (d.focus.isObject3D || d.focus.isVector3)))) throw fail(`dof.focus must be a distance from the camera, an Object3D or a Vector3, got ${JSON.stringify(d.focus)}`);
    if (typeof d.focus === "number") number("dof.focus", d.focus, 0, 1e9);
    number("dof.fStop", d.fStop, 0.5, 128); number("dof.unit", d.unit, 1e-6, 1e6); number("dof.maxBlur", d.maxBlur, 0, 64);
    if (d.blur !== null) number("dof.blur", d.blur, 0, 1000);
    choice("dof.quality", d.quality, Object.keys(QUALITY));
  }
  o.motionBlur = part("motionBlur");
  if (o.motionBlur) {
    const m = o.motionBlur;
    if (!Number.isInteger(m.samples) || m.samples < 1 || m.samples > 64) throw fail(`motionBlur.samples must be a whole number from 1 to 64, got ${JSON.stringify(m.samples)}`);
    number("motionBlur.shutter", m.shutter, 0, 360);
    if (m.samples > 1 && m.shutter > 0 && !o.update) throw fail("motionBlur needs update(t): the function that sets the scene to time t (it is called once per sample)");
  }
  return o;
}

/** The sub-frame times motion blur draws for the frame at `t` (seconds): `samples` times spread evenly over the
 * time the shutter is open (`shutter` degrees of a frame of 1/fps s), centred on `t`; the one nearest `t` last. */
export function shutterTimes(t, fps, samples, shutter) {
  if (samples <= 1 || shutter <= 0) return [t];
  const open = shutter / 360 / fps;
  const times = Array.from({length: samples}, (_, i) => t + ((i + 0.5) / samples - 0.5) * open);
  const nearest = times.reduce((best, x, i) => Math.abs(x - t) < Math.abs(times[best] - t) ? i : best, 0);
  return [...times.slice(0, nearest), ...times.slice(nearest + 1), times[nearest]];
}

/** The distance along the camera's view direction to `target` (an Object3D's world position or a Vector3). */
export function focusDistance(camera, target) {
  const p = target.isVector3 ? target.clone() : target.getWorldPosition(new THREE.Vector3());
  camera.updateMatrixWorld();
  return Math.max(1e-6, -p.applyMatrix4(camera.matrixWorldInverse).z);
}

/** The circle of confusion's radius in frame pixels far behind the focus (the `K` of r = K |z - zf| / z), for a
 * thin lens of the camera's focal length at `fStop`, focused at `focus` scene units (`unit` metres each). */
export function blurAtInfinity(camera, focus, fStop, unit, height) {
  const f = camera.getFocalLength(), zf = Math.max(focus * unit * 1000, f * 1.001);
  return (f * f / (fStop * (zf - f))) / 2 / camera.getFilmHeight() * height;
}

// ---------- the sensor (Step 397): the shaders' curves, in JavaScript too ----------
const srgbEncode = (x) => x <= 0.0031308 ? x * 12.92 : 1.055 * x ** (1 / 2.4) - 0.055;
/** The linear value the sensor clips at: `stops` above mid grey (0.18), after exposure. */
export function rangeWhite(stops) { return 0.18 * 2 ** stops; }
/** The limited dynamic range on one channel `v` of the tone-mapped picture (display-linear, 0..1), where `top`
 * is the tone curve's value of `rangeWhite(stops)`: from half of `top` the highlights are stretched so `top`
 * reaches 1, then clip with a soft shoulder `shoulder` wide; shadows crush as v² / (v + black), white kept. */
export function rangeCurve(v, top, {shoulder = 0.05, black = 0} = {}) {
  const a = top < 1 ? 1 / top - 1 : 0, k = 0.5 * top;
  const u = Math.min(1, Math.max(0, (v - k) / Math.max(top - k, 1e-6))), x = v * (1 + a * u * u * (3 - 2 * u));
  const q = Math.min(2 * shoulder, Math.max(0, x - 1 + shoulder));
  let y = shoulder > 0 ? Math.min(x, 1 + shoulder) - q * q / (4 * shoulder) : Math.min(x, 1);
  if (black > 0) y = y * y / (y + black) * (1 + black);
  return y;
}
/** The sensor noise's spread (a standard deviation, linear light) at the display-linear value `v` (0..1): shot
 * noise growing as √v over a read-noise floor, pressed by the tone curve's shoulder (× (1 − v²): a clipped
 * pixel has none), scaled so the encoded picture's noise at mid grey (0.18) is `amount` and the noise at black
 * is `floor` of the shot and read noise at mid grey. `noiseSpread(amount, floor, encoding)` gives
 * {scale, read} for sigma(v) = scale × √(v + read) × (1 − v²); `noiseSigma` that sigma. */
export function noiseSpread(amount, floor, encoding = "srgb") {
  const read = 0.18 * floor * floor / (1 - floor * floor), h = 1e-4;
  const encode = encoding === "srgb" ? srgbEncode : (x) => x ** (1 / 2.2);
  const slope = (encode(0.18 + h) - encode(0.18 - h)) / (2 * h);
  return {scale: amount / (slope * Math.sqrt(0.18 + read) * (1 - 0.18 * 0.18)), read};
}
export function noiseSigma(v, amount, floor, encoding = "srgb") {
  const {scale, read} = noiseSpread(amount, floor, encoding);
  return scale * Math.sqrt(Math.max(v, 0) + read) * (1 - Math.min(Math.max(v, 0), 1) ** 2);
}

// ---------- shaders ----------
const VERT = "varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }";
const quad = (fragmentShader, uniforms, defines = {}) => new THREE.ShaderMaterial({
  vertexShader: VERT, fragmentShader, uniforms, defines, depthTest: false, depthWrite: false, toneMapped: false});

const COPY = `varying vec2 vUv; uniform sampler2D tColor; uniform float uWeight;
void main() { gl_FragColor = vec4(texture2D(tColor, vUv).rgb * uWeight, 1.0); }`;

// Depth of field, step 1 (half size): gather a disc of samples (a golden-angle spiral). A sample counts where
// its own circle of confusion reaches this pixel; what lies in front bleeds over sharp things behind it, a
// blurred background does not bleed over a sharp foreground. Alpha keeps the largest circle that counted.
const DOF_GATHER = `#include <packing>
varying vec2 vUv; uniform sampler2D tColor, tDepth; uniform vec2 uPixel; uniform float uNear, uFar, uFocus, uK, uMaxR;
float viewZ(vec2 uv) {
  float d = texture2D(tDepth, uv).x;
#ifdef ORTHOGRAPHIC
  return -orthographicDepthToViewZ(d, uNear, uFar);
#else
  return -perspectiveDepthToViewZ(d, uNear, uFar);
#endif
}
float coc(float z) { return clamp(uK * abs(z - uFocus) / max(z, 1e-5), 0.0, uMaxR); }
void main() {
  float z0 = viewZ(vUv), r0 = coc(z0);
  vec3 acc = texture2D(tColor, vUv).rgb; float wsum = 1.0, cover = r0, reach = max(r0, uMaxR * 0.6);
  for (int i = 1; i < TAPS; i++) {
    float fi = float(i), rr = sqrt(fi / float(TAPS)) * reach, th = fi * 2.39996323;
    vec2 uv = vUv + vec2(cos(th), sin(th)) * rr * uPixel;
    float zs = viewZ(uv), rs = coc(zs);
    float w = smoothstep(rr - 1.0, rr + 1.0, zs > z0 ? min(rs, r0 + 1.0) : rs);
    acc += min(texture2D(tColor, uv).rgb, vec3(24.0)) * w; wsum += w; cover = max(cover, rs * w);
  }
  gl_FragColor = vec4(acc / wsum, cover);
}`;
// step 2 (frame size): the sharp picture where the lens is in focus, the gathered one where it is not
const DOF_MIX = `varying vec2 vUv; uniform sampler2D tColor, tBlur;
void main() { vec4 b = texture2D(tBlur, vUv); gl_FragColor = vec4(mix(texture2D(tColor, vUv).rgb, b.rgb, smoothstep(0.6, 2.6, b.a)), 1.0); }`;

// The grade: linear in, display-encoded (sRGB) out.
const TONE = THREE.ShaderChunk.tonemapping_pars_fragment.replace("uniform float toneMappingExposure;", "const float toneMappingExposure = 1.0;");
const GRADE = `${TONE}
varying vec2 vUv; uniform sampler2D tColor; uniform vec2 uAspect; uniform float uFringe, uVigAmount, uVigInner, uVigOuter, uSat, uContrast, uFade;
uniform vec3 uLinear, uFlash, uLift, uGamma, uGain;
vec3 narkowicz(vec3 x) { return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }
vec3 toneCurve(vec3 c) {
#if TONE_MAP == 1
  return ACESFilmicToneMapping(c);
#elif TONE_MAP == 2
  return AgXToneMapping(c);
#elif TONE_MAP == 3
  return NeutralToneMapping(c);
#elif TONE_MAP == 4
  return narkowicz(c);
#else
  return c;
#endif
}
#ifdef RANGE
uniform float uWhite, uShoulder, uBlack;
// rangeCurve of the module, per channel
vec3 range(vec3 v) {
  float top = clamp(toneCurve(vec3(uWhite)).g, 1e-3, 1.0), a = 1.0 / top - 1.0;
  vec3 x = v * (1.0 + a * smoothstep(vec3(0.5 * top), vec3(top), v));
  vec3 q = clamp(x - 1.0 + uShoulder, 0.0, 2.0 * uShoulder);
  vec3 y = uShoulder > 0.0 ? min(x, 1.0 + uShoulder) - q * q / (4.0 * uShoulder) : min(x, 1.0);
  return uBlack > 0.0 ? y * y / (y + uBlack) * (1.0 + uBlack) : y;
}
#endif
vec3 encode(vec3 c) {
#ifdef GAMMA22
  return pow(c, vec3(1.0 / 2.2));
#else
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
#endif
}
void main() {
  vec2 q = vUv - 0.5, qa = q * uAspect;
  float r = length(qa) / length(0.5 * uAspect);
  vec3 c;
  if (uFringe > 0.0) { vec2 o = q * dot(qa, qa) * uFringe * 0.02; c = vec3(texture2D(tColor, vUv + o).r, texture2D(tColor, vUv).g, texture2D(tColor, vUv - o).b); }
  else c = texture2D(tColor, vUv).rgb;
  c = max(c, 0.0) * uLinear + uFlash;
  c *= mix(1.0, smoothstep(uVigOuter, uVigInner, r), uVigAmount);
  c = toneCurve(c);
  c = clamp(c, 0.0, 1.0);
#ifdef RANGE
  c = range(c);
#endif
  c = max(mix(vec3(dot(c, vec3(0.2126, 0.7152, 0.0722))), c, uSat), 0.0);
  c = encode(clamp(c, 0.0, 1.0));
  c = (c - 0.5) * uContrast + 0.5;
  c = uGain * (c + uLift * (1.0 - c));
  c = pow(max(c, 0.0), 1.0 / uGamma);
  gl_FragColor = vec4(clamp(c, 0.0, 1.0) * uFade, 1.0);
}`;
// last: FXAA on the encoded picture, then the film grain (two hashes of the pixel and the frame number); with the
// sensor: sharpening after FXAA, then the sensor's noise in place of the grain
const OUTPUT = `varying vec2 vUv; uniform sampler2D tColor; uniform vec2 uPixel; uniform float uGrain, uSeed;
float hash(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
float luma(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }
#ifdef SHARPEN
uniform float uSharpen, uSharpRadius, uSharpLimit;
#endif
#ifdef NOISE
uniform float uNoiseScale, uNoiseRead, uNoiseColor, uNoiseSize, uFade;
vec3 hash3(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973)); p3 += dot(p3, p3.yxz + 33.33); return fract((p3.xxy + p3.yzz) * p3.zyx); }
// three noises of unit spread (one hash) for a cell of a grid \`size\` pixels wide
vec3 corner(vec2 cell, float salt) { return (hash3(cell + uSeed * vec2(13.7, 7.3) + salt) - 0.5) * 3.464; }
// the sensor's pixels larger than the frame's: one noise a cell, spread bilinearly over the frame's pixels from the
// cells' corners, its spread kept (divided by the weights' length)
vec3 cells(vec2 frag, float size, float salt) {
  vec2 p = frag / size - 0.5, i = floor(p), f = p - i;
  vec4 w = vec4((1.0 - f.x) * (1.0 - f.y), f.x * (1.0 - f.y), (1.0 - f.x) * f.y, f.x * f.y);
  vec3 n = corner(i, salt) * w.x + corner(i + vec2(1.0, 0.0), salt) * w.y + corner(i + vec2(0.0, 1.0), salt) * w.z + corner(i + 1.0, salt) * w.w;
  return n / length(w);
}
#ifdef GAMMA22
vec3 decode(vec3 c) { return pow(c, vec3(2.2)); }
vec3 encode(vec3 c) { return pow(c, vec3(1.0 / 2.2)); }
#else
vec3 decode(vec3 c) { return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c)); }
vec3 encode(vec3 c) { return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c)); }
#endif
#endif
void main() {
  vec3 c = texture2D(tColor, vUv).rgb;
#ifdef FXAA
  float lM = luma(c), lNW = luma(texture2D(tColor, vUv + vec2(-1.0, 1.0) * uPixel).rgb), lNE = luma(texture2D(tColor, vUv + vec2(1.0, 1.0) * uPixel).rgb),
        lSW = luma(texture2D(tColor, vUv + vec2(-1.0, -1.0) * uPixel).rgb), lSE = luma(texture2D(tColor, vUv + vec2(1.0, -1.0) * uPixel).rgb);
  float lMin = min(lM, min(min(lNW, lNE), min(lSW, lSE))), lMax = max(lM, max(max(lNW, lNE), max(lSW, lSE)));
  if (lMax - lMin > max(0.03, lMax * 0.1)) {
    vec2 dir = vec2(-((lNW + lNE) - (lSW + lSE)), (lNW + lSW) - (lNE + lSE));
    float reduce = max((lNW + lNE + lSW + lSE) * 0.03125, 1.0 / 128.0), scale = 1.0 / (min(abs(dir.x), abs(dir.y)) + reduce);
    dir = clamp(dir * scale, -8.0, 8.0) * uPixel;
    vec3 a = 0.5 * (texture2D(tColor, vUv + dir * (1.0 / 3.0 - 0.5)).rgb + texture2D(tColor, vUv + dir * (2.0 / 3.0 - 0.5)).rgb);
    vec3 b = a * 0.5 + 0.25 * (texture2D(tColor, vUv - dir * 0.5).rgb + texture2D(tColor, vUv + dir * 0.5).rgb);
    float lB = luma(b); c = (lB < lMin || lB > lMax) ? a : b;
  }
#endif
#ifdef SHARPEN
  // in-camera sharpening: the luma's detail against 4 samples \`radius\` pixels away, its halo held to \`limit\`
  vec2 r = uSharpRadius * uPixel;
  vec3 ring = texture2D(tColor, vUv + vec2(r.x, 0.0)).rgb + texture2D(tColor, vUv - vec2(r.x, 0.0)).rgb
            + texture2D(tColor, vUv + vec2(0.0, r.y)).rgb + texture2D(tColor, vUv - vec2(0.0, r.y)).rgb;
  float detail = luma(texture2D(tColor, vUv).rgb) - luma(ring) * 0.25;
  c = clamp(c + clamp(detail * uSharpen, -uSharpLimit, uSharpLimit), 0.0, 1.0);
#endif
#ifdef NOISE
  // the sensor's noise in linear light (noiseSigma): shot noise (√signal) over a read-noise floor, none where it clips; luma at the sensor's
  // pixels, colour on cells twice as wide (demosaicing smears it); blue noisiest, green least (white balance gains)
#ifdef NOISE_PIXEL
  float y = (corner(floor(gl_FragCoord.xy), 0.0).x + corner(floor(gl_FragCoord.xy) * 1.31, 57.0).x) * 0.7071;   // the sensor's pixels are the frame's
#else
  float y = cells(gl_FragCoord.xy, uNoiseSize, 0.0).x;
#endif
  vec3 lin = decode(c), n = mix(vec3(y), cells(gl_FragCoord.xy, 2.0 * uNoiseSize, 101.0), uNoiseColor);
  n *= vec3(1.15, 0.85, 1.3) / sqrt(uNoiseColor * uNoiseColor + (1.0 - uNoiseColor) * (1.0 - uNoiseColor));
  vec3 v = clamp(lin, 0.0, 1.0);
  c = encode(max(lin + n * uNoiseScale * sqrt(v + uNoiseRead) * (1.0 - v * v) * uFade, 0.0));
#else
  if (uGrain > 0.0) {
    float l = luma(c), n = hash(gl_FragCoord.xy + uSeed * 7.31) + hash(gl_FragCoord.xy * 1.7 + uSeed * 3.17 + 91.0) - 1.0;
    c += n * uGrain * (0.5 + 0.8 * (1.0 - l)) * smoothstep(0.0, 0.04, l + 0.02);
  }
#endif
  gl_FragColor = vec4(c, 1.0);
}`;

const TONE_INDEX = {none: 0, aces: 1, agx: 2, neutral: 3, "aces-narkowicz": 4};
const target = (w, h, extra = {}) => new THREE.WebGLRenderTarget(Math.max(1, w), Math.max(1, h), {type: THREE.HalfFloatType, depthBuffer: false, ...extra});

// ---------- the chain ----------
export class Finish {
  /** `renderer`, `scene`, `camera` as the page made them; `ctx` the page's (for fps and size); `options`: see the guide. */
  constructor(renderer, scene, camera, ctx, options = {}) {
    if (!renderer || !renderer.isWebGLRenderer) throw fail("the first argument must be the page's THREE.WebGLRenderer");
    if (!scene || !scene.isScene) throw fail("the second argument must be a THREE.Scene");
    if (!camera || !camera.isCamera) throw fail("the third argument must be a THREE.Camera");
    if (!ctx || !Number.isFinite(ctx.fps)) throw fail("the fourth argument must be the ctx vidgen gives load(ctx)");
    this.renderer = renderer; this.scene = scene; this.camera = camera; this.fps = ctx.fps;
    this.raw = {...options};
    this.options = resolveOptions(this.raw, 0);
    const size = renderer.getDrawingBufferSize(new THREE.Vector2());
    this.width = size.x; this.height = size.y;
    this.fsq = new FullScreenQuad();
    this.copy = quad(COPY, {tColor: {value: null}, uWeight: {value: 1}});
    this.add = quad(COPY, {tColor: {value: null}, uWeight: {value: 1}});
    this.add.blending = THREE.CustomBlending; this.add.blendSrc = THREE.OneFactor; this.add.blendDst = THREE.OneFactor; this.add.transparent = true;
    this.gradeMaterials = {};
    this.gatherMaterials = {};
    this.mix = quad(DOF_MIX, {tColor: {value: null}, tBlur: {value: null}});
    this.outputMaterials = {};
    this.targets = {};
  }

  /** Change options (merged into those given so far); a value may be a function of t. */
  set(options) {
    this.raw = {...this.raw, ...options};
    this.options = resolveOptions(this.raw, this.lastTime ?? 0);
    return this;
  }

  _target(name, w, h, extra) {
    let rt = this.targets[name];
    if (rt && (rt.width !== w || rt.height !== h)) { rt.dispose(); rt = null; }
    if (!rt) rt = this.targets[name] = target(w, h, extra);
    return rt;
  }
  _sceneTarget(w, h) {
    let rt = this.targets.scene;
    if (rt && (rt.width !== w || rt.height !== h)) { rt.dispose(); rt = null; }
    if (!rt) rt = this.targets.scene = target(w, h, {depthBuffer: true, depthTexture: new THREE.DepthTexture(w, h, THREE.UnsignedIntType)});
    return rt;
  }
  _pass(material, out) {
    this.fsq.material = material;
    this.renderer.setRenderTarget(out);
    this.fsq.render(this.renderer);
  }
  _drawScene(rt) {
    const r = this.renderer;
    if (r.shadowMap.enabled && !r.shadowMap.autoUpdate) r.shadowMap.needsUpdate = true;
    r.setRenderTarget(rt); r.clear(); r.render(this.scene, this.camera);
  }

  /** Draw the frame at `t` (seconds of the scene) to the canvas. */
  render(t) {
    const r = this.renderer, o = resolveOptions(this.raw, t);
    this.options = o; this.lastTime = t;
    const W = this.width, H = this.height;
    const sw = Math.round(W * o.renderScale), sh = Math.round(H * o.renderScale);
    const sceneRT = this._sceneTarget(sw, sh);
    const autoClear = r.autoClear, clearColor = r.getClearColor(new THREE.Color()), clearAlpha = r.getClearAlpha();
    r.autoClear = false;
    const times = o.motionBlur ? shutterTimes(t, this.fps, o.motionBlur.samples, o.motionBlur.shutter) : [t];
    let picture = sceneRT;
    if (times.length > 1) {
      const acc = this._target("accumulate", sw, sh);
      r.setRenderTarget(acc); r.setClearColor(0x000000, 0); r.clear(); r.setClearColor(clearColor, clearAlpha);
      for (const time of times) {
        o.update(time);
        this._drawScene(sceneRT);
        this.add.uniforms.tColor.value = sceneRT.texture; this.add.uniforms.uWeight.value = 1 / times.length;
        this._pass(this.add, acc);
      }
      if (times[times.length - 1] !== t) o.update(t);
      picture = acc;
    } else {
      if (o.update) o.update(t);
      this._drawScene(sceneRT);
    }
    // options given as functions of t are read again now that the scene stands at t (a focus on a moving object)
    Object.assign(o, resolveOptions(this.raw, t), {motionBlur: o.motionBlur, renderScale: o.renderScale});
    this.options = o;
    // depth of field, or the picture at the frame's size
    let hdr = picture;
    const K = o.dof ? this._blur(o.dof) : 0;
    if (o.dof && K > 0) {
      const q = QUALITY[o.dof.quality], gw = q.half ? sw >> 1 : sw, gh = q.half ? sh >> 1 : sh;
      const gather = this._gather(q.taps);
      const u = gather.uniforms;
      u.tColor.value = picture.texture; u.tDepth.value = sceneRT.depthTexture; u.uPixel.value.set(1 / W, 1 / H);
      u.uNear.value = this.camera.near; u.uFar.value = this.camera.far; u.uFocus.value = this._focus(o.dof);
      u.uK.value = K; u.uMaxR.value = o.dof.maxBlur * H / 720;
      this._pass(gather, this._target("blur", gw, gh));
      hdr = this._target("frame", W, H);
      this.mix.uniforms.tColor.value = picture.texture; this.mix.uniforms.tBlur.value = this.targets.blur.texture;
      this._pass(this.mix, hdr);
    } else if (sw !== W || sh !== H) {
      hdr = this._target("frame", W, H);
      this.copy.uniforms.tColor.value = picture.texture; this.copy.uniforms.uWeight.value = 1;
      this._pass(this.copy, hdr);
    }
    if (o.bloom && o.bloom.strength > 0) {
      const bloom = this._bloom(Math.round(W * o.bloom.scale), Math.round(H * o.bloom.scale));
      bloom.strength = o.bloom.strength; bloom.radius = o.bloom.radius; bloom.threshold = o.bloom.threshold;
      bloom.render(r, null, hdr, 0, false);
    }
    // grade, then FXAA and grain to the canvas
    const range = o.range.stops > 0, noise = o.noise.amount > 0, sharpen = o.sharpen.amount > 0;
    const grade = this._grade(o.toneMapping, o.encoding, range), u = grade.uniforms, g = o.grade;
    const wb = [1 + 0.25 * g.temperature, 1 - 0.2 * g.tint, 1 - 0.25 * g.temperature];
    const lum = 0.2126 * wb[0] + 0.7152 * wb[1] + 0.0722 * wb[2];
    u.tColor.value = hdr.texture; u.uAspect.value.set(W / H, 1); u.uFringe.value = o.fringe;
    u.uLinear.value.set(o.exposure * g.filter[0] * wb[0] / lum, o.exposure * g.filter[1] * wb[1] / lum, o.exposure * g.filter[2] * wb[2] / lum);
    u.uFlash.value.set(...o.flash.color).multiplyScalar(o.flash.amount);
    u.uVigAmount.value = o.vignette.amount; u.uVigInner.value = o.vignette.inner; u.uVigOuter.value = o.vignette.outer;
    u.uSat.value = g.saturation; u.uContrast.value = g.contrast; u.uFade.value = o.fade;
    u.uLift.value.set(...g.lift); u.uGamma.value.set(...g.gamma); u.uGain.value.set(...g.gain);
    if (range) { u.uWhite.value = rangeWhite(o.range.stops); u.uShoulder.value = o.range.shoulder; u.uBlack.value = o.range.black; }
    if (o.antialias === "none" && o.grain === 0 && !noise && !sharpen) {
      this._pass(grade, null);
    } else {
      const ldr = this._target("display", W, H, {type: THREE.UnsignedByteType});
      this._pass(grade, ldr);
      const out = this._output(o.antialias === "fxaa", noise ? o.encoding : null, sharpen, noise && o.noise.size * H / 720 <= 1), ou = out.uniforms;
      ou.tColor.value = ldr.texture; ou.uPixel.value.set(1 / W, 1 / H); ou.uGrain.value = o.grain * o.fade;
      ou.uSeed.value = Math.round(t * this.fps) % 4096;
      if (sharpen) { ou.uSharpen.value = o.sharpen.amount; ou.uSharpRadius.value = o.sharpen.radius * H / 720; ou.uSharpLimit.value = o.sharpen.limit; }
      if (noise) {
        const spread = noiseSpread(o.noise.amount, o.noise.floor, o.encoding);
        ou.uNoiseScale.value = spread.scale; ou.uNoiseRead.value = spread.read; ou.uNoiseColor.value = o.noise.color;
        ou.uNoiseSize.value = o.noise.size * H / 720; ou.uFade.value = o.fade;
      }
      this._pass(out, null);
    }
    r.autoClear = autoClear;
  }

  /** Compile every shader of the scene and of the chain and draw the frame at `t` once (in load): frame 0 then
   * pays no compile time. Waits for the GPU with a one-pixel read. Not compileAsync: its polling timer never
   * fires while vidgen's clock stands still in load. */
  warmUp(t = 0) {
    const r = this.renderer, o = resolveOptions(this.raw, t);
    if (o.update) o.update(t);
    const W = this.width, H = this.height;
    r.setRenderTarget(this._sceneTarget(Math.round(W * o.renderScale), Math.round(H * o.renderScale)));
    r.compile(this.scene, this.camera);
    this.render(t);
    const gl = r.getContext();
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(4));
    return this;
  }

  _focus(d) { return typeof d.focus === "number" ? d.focus : focusDistance(this.camera, d.focus); }
  _blur(d) {
    if (d.blur !== null) return d.blur * this.height / 720;
    if (!this.camera.isPerspectiveCamera) throw fail("dof.fStop needs a PerspectiveCamera; give dof.blur (pixels at 720p) for another camera");
    return blurAtInfinity(this.camera, this._focus(d), d.fStop, d.unit, this.height);
  }
  _gather(taps) {
    const key = `${taps}${this.camera.isOrthographicCamera ? "o" : "p"}`;
    return this.gatherMaterials[key] ??= quad(DOF_GATHER, {tColor: {value: null}, tDepth: {value: null}, uPixel: {value: new THREE.Vector2()},
      uNear: {value: 1}, uFar: {value: 100}, uFocus: {value: 10}, uK: {value: 0}, uMaxR: {value: 10}},
      this.camera.isOrthographicCamera ? {TAPS: taps, ORTHOGRAPHIC: 1} : {TAPS: taps});
  }
  _grade(tone, encoding, range) {
    const defines = {TONE_MAP: TONE_INDEX[tone], ...(encoding === "gamma2.2" ? {GAMMA22: 1} : {}), ...(range ? {RANGE: 1} : {})};
    return this.gradeMaterials[`${tone} ${encoding}${range ? " range" : ""}`] ??= quad(GRADE, {tColor: {value: null}, uAspect: {value: new THREE.Vector2(1, 1)}, uFringe: {value: 0},
      uVigAmount: {value: 0}, uVigInner: {value: 0.3}, uVigOuter: {value: 1.2}, uSat: {value: 1}, uContrast: {value: 1}, uFade: {value: 1},
      uLinear: {value: new THREE.Vector3(1, 1, 1)}, uFlash: {value: new THREE.Vector3()}, uLift: {value: new THREE.Vector3()},
      uGamma: {value: new THREE.Vector3(1, 1, 1)}, uGain: {value: new THREE.Vector3(1, 1, 1)},
      uWhite: {value: 1}, uShoulder: {value: 0}, uBlack: {value: 0}}, defines);
  }
  /** The last pass: FXAA or not; `noiseEncoding` the picture's encoding when the sensor's noise is on (else null);
   * sharpening or not; `pixel`: the noise's cells are the frame's pixels (no spreading). */
  _output(fxaa, noiseEncoding, sharpen, pixel) {
    const defines = {...(fxaa ? {FXAA: 1} : {}), ...(noiseEncoding ? {NOISE: 1} : {}), ...(noiseEncoding === "gamma2.2" ? {GAMMA22: 1} : {}),
      ...(sharpen ? {SHARPEN: 1} : {}), ...(pixel ? {NOISE_PIXEL: 1} : {})};
    return this.outputMaterials[`${fxaa} ${noiseEncoding} ${sharpen} ${pixel}`] ??= quad(OUTPUT, {tColor: {value: null}, uPixel: {value: new THREE.Vector2()}, uGrain: {value: 0}, uSeed: {value: 0},
      uSharpen: {value: 0}, uSharpRadius: {value: 1}, uSharpLimit: {value: 0},
      uNoiseScale: {value: 0}, uNoiseRead: {value: 0}, uNoiseColor: {value: 0}, uNoiseSize: {value: 1}, uFade: {value: 1}}, defines);
  }
  _bloom(w, h) {
    if (this.bloomPass && (this.bloomPass.resolution.x !== w || this.bloomPass.resolution.y !== h)) { this.bloomPass.dispose(); this.bloomPass = null; }
    return this.bloomPass ??= new UnrealBloomPass(new THREE.Vector2(w, h), 0.35, 0.5, 1);
  }

  /** Free the render targets and materials. */
  dispose() {
    for (const rt of Object.values(this.targets)) rt.dispose();
    for (const m of [this.copy, this.add, this.mix, ...Object.values(this.gradeMaterials), ...Object.values(this.gatherMaterials), ...Object.values(this.outputMaterials)]) m.dispose();
    if (this.bloomPass) this.bloomPass.dispose();
    this.fsq.dispose();
  }
}

// ---------- shadows ----------
/** Soft shadows with what three.js 0.186 offers (PCFSoftShadowMap is gone; it falls back to PCF): `"pcf"`
 * (hardware-filtered 5-tap disc rotated per pixel; `radius` in shadow-map texels) or `"vsm"` (variance shadow
 * map, blurred with `blurSamples`; smooth, but every receiver also casts). Sets the renderer and the light. */
export function softShadows(renderer, light, {type = "pcf", radius = 2, mapSize = 2048, blurSamples = 8, bias = -0.0004, normalBias = 0.02} = {}) {
  choice("softShadows type", type, ["pcf", "vsm"]);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = type === "vsm" ? THREE.VSMShadowMap : THREE.PCFShadowMap;
  light.castShadow = true;
  light.shadow.mapSize.set(mapSize, mapSize);
  light.shadow.radius = number("softShadows radius", radius, 0, 64);
  light.shadow.blurSamples = blurSamples;
  light.shadow.bias = bias; light.shadow.normalBias = normalBias;
  if (light.shadow.map) { light.shadow.map.dispose(); light.shadow.map = null; }
  return light;
}

// ---------- environments ----------
const SKY_VERT = "varying vec3 vDir; void main() { vDir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }";
const STUDIO_FRAG = `varying vec3 vDir;
uniform vec3 uL[8], uU[8], uC[8]; uniform vec4 uS[8]; uniform vec3 uSky, uGround, uUp; uniform int uN;
void main() {
  vec3 d = normalize(vDir), col = mix(uGround, uSky, smoothstep(-0.3, 0.6, dot(d, uUp)));
  for (int i = 0; i < 8; i++) {
    if (i >= uN) break;
    float dl = dot(d, uL[i]);
    if (dl > 0.05) {
      vec3 V = cross(uL[i], uU[i]); vec2 p = vec2(dot(d, uU[i]), dot(d, V)) / dl; float s = uS[i].z;
      float m = (1.0 - smoothstep(uS[i].x - s, uS[i].x + s, abs(p.x))) * (1.0 - smoothstep(uS[i].y - s, uS[i].y + s, abs(p.y)));
      col += uC[i] * m * (1.0 + uS[i].w * p.x);
    }
  }
  gl_FragColor = vec4(col, 1.0);
}`;
// soft boxes of a product studio, y up: a big warm key above left, a cool strip right, a warm rim low, a
// cool rim high, two small hard lights for sparkle, a faint warm fill from the front
const STUDIO_PRESETS = {
  studio: {sky: 0x101216, ground: 0x0a0806, boxes: [
    {direction: [-0.5, 0.6, 0.62], size: [0.5, 0.36], softness: 0.42, gradient: 0.3, color: 0xfff0dc, intensity: 1.25},
    {direction: [0.86, 0.48, 0.15], across: [0, 0, 1], size: [0.13, 0.9], softness: 0.06, color: 0xcfe2ff, intensity: 1.5},
    {direction: [-0.2, 0.33, 0.92], size: [1.1, 0.1], softness: 0.06, color: 0xffd9b0, intensity: 0.9},
    {direction: [0.3, 0.2, -0.93], size: [0.8, 0.09], softness: 0.05, color: 0xbcd4ff, intensity: 1.1},
    {direction: [-0.88, 0.46, -0.1], across: [0, 0, 1], size: [0.045, 0.045], softness: 0.02, color: 0xffffff, intensity: 18},
    {direction: [0.5, 0.76, -0.42], size: [0.03, 0.03], softness: 0.015, color: 0xfff2dd, intensity: 26},
    {direction: [0.1, 1, 0.1], size: [0.9, 0.9], softness: 0.8, gradient: 0.5, color: 0xfff4e6, intensity: 0.34},
  ]},
  cool: {sky: 0x0a0d14, ground: 0x050608, boxes: [
    {direction: [-0.5, 0.6, 0.62], size: [0.5, 0.36], softness: 0.42, gradient: 0.3, color: 0xdde9ff, intensity: 1.2},
    {direction: [0.86, 0.48, 0.15], across: [0, 0, 1], size: [0.12, 0.9], softness: 0.06, color: 0x9fc0ff, intensity: 1.3},
    {direction: [-0.2, 0.33, 0.92], size: [1.1, 0.09], softness: 0.06, color: 0xffc890, intensity: 0.7},
    {direction: [0.5, 0.76, -0.42], size: [0.03, 0.03], softness: 0.015, color: 0xffffff, intensity: 22},
    {direction: [0.1, 1, 0.1], size: [0.9, 0.9], softness: 0.8, gradient: 0.5, color: 0xe6f0ff, intensity: 0.3},
  ]},
  soft: {sky: 0x24262a, ground: 0x121110, boxes: [
    {direction: [-0.4, 0.7, 0.6], size: [0.9, 0.7], softness: 0.6, gradient: 0.2, color: 0xfff6ec, intensity: 1.1},
    {direction: [0.8, 0.4, 0.3], across: [0, 0, 1], size: [0.4, 0.9], softness: 0.4, color: 0xe4eeff, intensity: 0.7},
  ]},
};
const BOX_KEYS = ["direction", "across", "size", "softness", "gradient", "color", "intensity"];

/** A studio of soft boxes on a dark dome, baked once through PMREM: the texture for `scene.environment`
 * (metal needs something to reflect). `preset`: "studio" (warm key, cool strip, rims, sparkles), "cool", "soft";
 * or your own `boxes` [{direction, across, size: [half-width, half-height] as tangents, softness, gradient,
 * color, intensity}] (up to 8), `sky` / `ground` colours, `up` (the dome's up and the preset's +y), `blur`. */
export function studioEnvironment(renderer, {preset = "studio", boxes = null, sky = null, ground = null, up = [0, 1, 0], blur = 0.02, intensity = 1} = {}) {
  choice("studioEnvironment preset", preset, Object.keys(STUDIO_PRESETS));
  const base = STUDIO_PRESETS[preset], list = boxes ?? base.boxes;
  if (!Array.isArray(list) || list.length > 8) throw fail("studioEnvironment boxes must be a list of at most 8 boxes");
  const upV = new THREE.Vector3(...up).normalize();
  const turn = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), upV);
  const u = {uL: {value: []}, uU: {value: []}, uS: {value: []}, uC: {value: []}, uN: {value: list.length}, uUp: {value: upV},
    uSky: {value: new THREE.Color(sky ?? base.sky)}, uGround: {value: new THREE.Color(ground ?? base.ground)}};
  for (let i = 0; i < 8; i++) {
    const b = list[i] ?? {direction: [0, 1, 0], size: [0, 0], intensity: 0};
    for (const k of Object.keys(b)) if (!BOX_KEYS.includes(k)) throw unknown(`boxes[${i}].`, k, BOX_KEYS);
    const L = new THREE.Vector3(...b.direction).normalize(), A = new THREE.Vector3(...(b.across ?? [1, 0, 0]));
    if (!boxes) { L.applyQuaternion(turn); A.applyQuaternion(turn); }
    A.addScaledVector(L, -A.dot(L)).normalize();
    u.uL.value.push(L); u.uU.value.push(A);
    u.uS.value.push(new THREE.Vector4(b.size[0], b.size[1], b.softness ?? 0.1, b.gradient ?? 0));
    u.uC.value.push(new THREE.Color(b.color ?? 0xffffff).multiplyScalar((b.intensity ?? 1) * intensity));
  }
  const scene = new THREE.Scene(), material = new THREE.ShaderMaterial({uniforms: u, vertexShader: SKY_VERT, fragmentShader: STUDIO_FRAG, side: THREE.BackSide});
  const geometry = new THREE.SphereGeometry(50, 48, 24);
  scene.add(new THREE.Mesh(geometry, material));
  const pmrem = new THREE.PMREMGenerator(renderer);
  const rt = pmrem.fromScene(scene, blur, 1, 200);
  pmrem.dispose(); material.dispose(); geometry.dispose();
  return rt.texture;
}

const NEBULA_FRAG = `varying vec3 vDir; uniform vec3 uOffset, uDeep, uMid, uBright, uGlow; uniform float uDensity, uStars;
float hash(vec3 p) { p = fract(p * 0.3183099 + vec3(0.1, 0.2, 0.3)); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float noise(vec3 p) {
  vec3 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash(i), hash(i + vec3(1, 0, 0)), f.x), mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
             mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x), mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}
float fbm(vec3 p) { float a = 0.5, s = 0.0; for (int i = 0; i < 6; i++) { s += a * noise(p); p = p * 2.02 + vec3(17.1, 9.4, 3.7); a *= 0.5; } return s; }
float stars(vec3 d, float scale, float cut) {
  vec3 q = d * scale, c = floor(q); float h = hash(c + uOffset);
  vec3 o = vec3(hash(c + 3.1), hash(c + 7.7), hash(c + 13.3)) * 0.6 + 0.2; float m = hash(c + 21.0);
  return step(cut, h) * smoothstep(0.16 + 0.14 * m * m, 0.0, length(q - c - o)) * (0.15 + 0.85 * m * m * m);
}
void main() {
  vec3 d = normalize(vDir), s = uOffset;
  vec3 w = d + 0.55 * (vec3(fbm(d * 1.6 + s + 11.0), fbm(d * 1.6 + s + 23.0), fbm(d * 1.6 + s + 37.0)) - 0.5);
  float dens = smoothstep(0.62 - 0.3 * uDensity, 1.02 - 0.3 * uDensity, fbm(w * 2.1 + s) + 0.3);
  float fil = 1.0 - abs(2.0 * fbm(w * 4.3 + s * 1.7 + 5.0) - 1.0); fil = fil * fil * fil;
  float dust = smoothstep(0.42, 0.7, fbm(w * 3.1 + 50.0 - s));
  vec3 c = uDeep + uMid * dens + uBright * dens * dens * (0.25 + 1.5 * fil) + uGlow * pow(max(dot(d, normalize(vec3(0.3, 0.2, -1.0))), 0.0), 6.0) * (0.3 + dens);
  c *= 1.0 - 0.6 * dust;
  float st = stars(d, 90.0, 0.93) * 1.6 + stars(d, 170.0, 0.90) * 0.9 + stars(d, 300.0, 0.88) * 0.5;
  c += vec3(0.75, 0.86, 1.0) * st * uStars * (1.0 - 0.75 * dens);
  gl_FragColor = vec4(c, 1.0);
}`;
function seeded(seed) { // mulberry32: three offsets from an integer seed
  let a = seed >>> 0;
  const next = () => { a = (a + 0x6D2B79F5) >>> 0; let x = a; x = Math.imul(x ^ (x >>> 15), x | 1); x ^= x + Math.imul(x ^ (x >>> 7), x | 61); return ((x ^ (x >>> 14)) >>> 0) / 4294967296; };
  return new THREE.Vector3(next() * 100, next() * 100, next() * 100);
}

/** A nebula with stars baked once into a cube map (half-float, linear): `{background, environment}` for
 * `scene.background` and, with `environment: true`, a PMREM texture for `scene.environment`. Same `seed`,
 * same sky. Colours are linear and may be brighter than 1 (they bloom). */
export function nebulaSky(renderer, {seed = 1, size = 512, deep = 0x010308, mid = 0x06203a, bright = 0x2a7fa0, glow = 0x000000, density = 0.5, stars = 1, environment = false} = {}) {
  if (!Number.isInteger(seed)) throw fail(`nebulaSky seed must be a whole number, got ${JSON.stringify(seed)}`);
  number("nebulaSky size", size, 16, 2048); number("nebulaSky density", density, 0, 1); number("nebulaSky stars", stars, 0, 10);
  const rt = new THREE.WebGLCubeRenderTarget(size, {type: THREE.HalfFloatType, magFilter: THREE.LinearFilter, minFilter: THREE.LinearFilter, generateMipmaps: false});
  const material = new THREE.ShaderMaterial({vertexShader: SKY_VERT, fragmentShader: NEBULA_FRAG, side: THREE.BackSide, depthTest: false, depthWrite: false,
    uniforms: {uOffset: {value: seeded(seed)}, uDeep: {value: new THREE.Color(deep)}, uMid: {value: new THREE.Color(mid)}, uBright: {value: new THREE.Color(bright)},
      uGlow: {value: new THREE.Color(glow)}, uDensity: {value: density}, uStars: {value: stars}}});
  const geometry = new THREE.BoxGeometry(20, 20, 20), scene = new THREE.Scene();
  scene.add(new THREE.Mesh(geometry, material));
  new THREE.CubeCamera(1, 100, rt).update(renderer, scene);
  material.dispose(); geometry.dispose();
  let env = null;
  if (environment) { const pmrem = new THREE.PMREMGenerator(renderer); env = pmrem.fromCubemap(rt.texture).texture; pmrem.dispose(); }
  return {background: rt.texture, environment: env};
}

// ---------- surface finishes ----------
const TAU = Math.PI * 2;
const HEIGHTS = {
  // straight graining (brushed steel), a little wavy
  brushed: (u, v) => 0.5 * Math.sin(v * 256 * TAU / 3.1 + 2.2 * Math.sin(u * TAU)) + 0.4 * Math.sin(v * 256 * TAU / 7.3 + 1.3 * Math.sin(u * TAU * 2 + 1)),
  // Geneva stripes: two scalloped bands per tile, each crossed by the fine arcs of the cutter
  geneva: (u, v) => {
    const band = u * 2, f = band - Math.floor(band), side = Math.floor(band) % 2 ? 1 : -1;
    const arc = Math.sin((v * 46 + Math.sqrt(Math.max(0, 1 - (f * 2 - 1) ** 2)) * 5.5 * side) * TAU);
    return 0.9 * Math.pow(Math.sin(f * Math.PI), 0.6) + 0.045 * arc * Math.sin(f * Math.PI);
  },
  // perlage: overlapping spots of circular graining, each row laid over the one before
  perlage: (u, v) => {
    const n = 4; let best = 0, height = 0;
    for (let j = -1; j <= n; j++) for (let i = -1; i <= n; i++) {
      let dx = u - (i + (j % 2 ? 0.5 : 0) + 0.25) / n, dy = v - (j + 0.5) / n; dx -= Math.round(dx); dy -= Math.round(dy);
      const r = Math.hypot(dx, dy) * n;
      if (r < 0.62) { const order = ((j + 8) % n) * 10 + ((i + 8) % n) + 1; if (order > best) { best = order; height = 0.35 * Math.cos(r * 60) * (0.4 + r) + 0.6 * (1 - r * r); } }
    }
    return height;
  },
  // circular graining: fine rings about the middle of the texture (wheels, discs)
  circular: (u, v) => { const r = Math.hypot(u - 0.5, v - 0.5); return 0.5 * Math.sin(r * 1024 * TAU / 5.5) + 0.3 * Math.sin(r * 1024 * TAU / 17.3 + 1.7); },
  // sunray: fine radial lines (dials, crown wheels)
  sunray: (u, v) => { const a = Math.atan2(v - 0.5, u - 0.5); return 0.5 * Math.sin(a * 360) + 0.35 * Math.sin(a * 133 + 1.2) + 0.25 * Math.sin(a * 77 + 4); },
};
const TILES = {brushed: true, geneva: true, perlage: true, circular: false, sunray: false};
const STRENGTH = {brushed: 0.5, geneva: 5.5, perlage: 2.6, circular: 0.55, sunray: 0.6};

/** A procedural surface finish: `{normalMap, roughnessMap}` DataTextures (linear) from a height function.
 * `kind`: "brushed", "geneva", "perlage", "circular", "sunray". `roughness` [base, variation] sets the
 * roughness map (green channel, as three.js reads it; multiply by the material's roughness = 1). */
export function surfaceFinish(kind, {size = 512, strength = null, roughness = [0.3, 0.1], anisotropy = 4} = {}) {
  choice("surfaceFinish kind", kind, Object.keys(HEIGHTS));
  if (!Number.isInteger(size) || size < 16 || size > 2048) throw fail(`surfaceFinish size must be a whole number from 16 to 2048, got ${JSON.stringify(size)}`);
  const height = HEIGHTS[kind], wrap = TILES[kind], k = strength ?? STRENGTH[kind];
  const h = new Float32Array(size * size);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) h[y * size + x] = height((x + 0.5) / size, (y + 0.5) / size);
  let lo = Infinity, hi = -Infinity; for (const v of h) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  const at = (x, y) => wrap ? h[((y + size) % size) * size + ((x + size) % size)] : h[Math.min(size - 1, Math.max(0, y)) * size + Math.min(size - 1, Math.max(0, x))];
  const normal = new Uint8Array(size * size * 4), rough = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const dx = (at(x + 1, y) - at(x - 1, y)) * k, dy = (at(x, y + 1) - at(x, y - 1)) * k, l = 1 / Math.hypot(dx, dy, 1), i = (y * size + x) * 4;
    normal[i] = 127.5 - dx * l * 127.5; normal[i + 1] = 127.5 - dy * l * 127.5; normal[i + 2] = 127.5 + l * 127.5; normal[i + 3] = 255;
    const r = Math.min(1, Math.max(0, roughness[0] + roughness[1] * ((h[y * size + x] - lo) / (hi - lo || 1) - 0.5) * 2));
    rough[i] = rough[i + 1] = rough[i + 2] = Math.round(r * 255); rough[i + 3] = 255;
  }
  const texture = (data) => {
    const t = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
    t.wrapS = t.wrapT = wrap ? THREE.RepeatWrapping : THREE.ClampToEdgeWrapping;
    t.magFilter = THREE.LinearFilter; t.minFilter = THREE.LinearMipmapLinearFilter; t.generateMipmaps = true; t.anisotropy = anisotropy; t.needsUpdate = true;
    return t;
  };
  return {normalMap: texture(normal), roughnessMap: texture(rough)};
}
