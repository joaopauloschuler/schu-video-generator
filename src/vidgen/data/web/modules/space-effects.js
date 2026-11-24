// vidgen/space-effects: what the air does to a craft and a craft to the air (DESIGN.md §123.9): the glow of a
// re-entry (a shock layer on the windward side, hot surfaces, a wake, sparks, a far head with a luminous train),
// vapour trails laid in the WORLD, engine exhaust shaped by the air's pressure, the vapour of a transonic
// pass and of a hard turn. One call: `effects(craft, {flight: ctx.flight, name, sky, reentry, contrails, exhaust,
// vapour})`, `scene.add(fx.object)`, `fx.update(t)` after the craft's own update.
//
// Everything is a function of the time given to update() and of the flight: no state is kept between frames
// (a still at t is frame t of a clip), nothing is random without the seed. A trail is built each frame from
// the flight's past positions at birth times that are fixed multiples of a step, so a piece of trail stays
// where it was laid. The craft is anything with an `object` (a Craft, a Plane, a hull of your own, an
// Object3D): the effects take a bounding ellipsoid and named places (`anchors`), never a plane's internals.
// Axes of a craft as in vidgen/space-craft: +z the nose, +y up, +x the left wing. Units metres, seconds.
//
// What is physical and what is a look is said in DESIGN §123.9. In short: where things are and when (the
// windward side from the velocity, strength from the flight's heating, Mach number, load and height, the trail
// along the path flown, the plume widening as the air thins) follow the flight; shapes, colours, brightness
// and lifetimes are looks.
import * as THREE from "three";
import {AIR_GLSL, DISPLAY_GLSL, sunlightAt, skyAmbient} from "vidgen/space-air";

export const VERSION = 1;
const PREFIX = "vidgen/space-effects";
const TAU = Math.PI * 2;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const mix = (a, b, u) => a + (b - a) * u;
const smooth = (a, b, x) => { const u = clamp((x - a) / (b - a)); return u * u * (3 - 2 * u); };
const V3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
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
  return object;
}
// whole-number hash -> [0, 1): the same on every machine
export function hash(i, j = 0, seed = 1) {
  let h = (Math.imul(i | 0, 374761393) + Math.imul(j | 0, 668265263) + Math.imul(seed | 0, 2147483647)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177); h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}

// ---------- pure: what a number of the flight means for the picture ----------
/** The glow's colour by heating (0..1): dull red, orange, a white-pink at the peak. Linear, no part over 1. */
export const HEAT_STOPS = Object.freeze([[0, [0.55, 0.04, 0.0]], [0.3, [1.0, 0.13, 0.02]], [0.6, [1.0, 0.42, 0.08]], [0.85, [1.0, 0.7, 0.42]], [1, [1.0, 0.86, 0.9]]]);
/** Whites (a sunlit white ground = 1) of the shock layer's brightest part at heating 1: a look. */
export const HEAT_WHITES = 3.2;
export function heatColor(h) {
  const x = clamp(h);
  for (let i = 1; i < HEAT_STOPS.length; i++) if (x <= HEAT_STOPS[i][0]) { const [a, ca] = HEAT_STOPS[i - 1], [b, cb] = HEAT_STOPS[i], u = (x - a) / (b - a); return ca.map((c, k) => mix(c, cb[k], u)); }
  return HEAT_STOPS[HEAT_STOPS.length - 1][1].slice();
}
/** The glow's brightness by heating (0..1), in whites: nothing under 0.02, rising all the way (never falling). */
export const heatLevel = (h) => { const x = clamp(h); return HEAT_WHITES * Math.pow(x, 1.6) * smooth(0.02, 0.14, x); };
/** The glow's light at heating h: heatColor times heatLevel. */
export const heatLight = (h) => { const l = heatLevel(h); return heatColor(h).map((c) => c * l); };
const HEAT_GLSL = `vec3 heatColor(float h) { h = clamp(h, 0.0, 1.0); vec3 c = vec3(${HEAT_STOPS[0][1].map((v) => v.toFixed(3)).join(", ")});
${HEAT_STOPS.slice(1).map(([b, cb], i) => `  c = mix(c, vec3(${cb.map((v) => v.toFixed(3)).join(", ")}), clamp((h - ${HEAT_STOPS[i][0].toFixed(3)}) / ${(b - HEAT_STOPS[i][0]).toFixed(3)}, 0.0, 1.0));`).join("\n")}
  return c; }
float heatLevel(float h) { h = clamp(h, 0.0, 1.0); return ${HEAT_WHITES.toFixed(1)} * pow(h, 1.6) * smoothstep(0.02, 0.14, h); }
vec3 heatLight(float h) { return heatColor(h) * heatLevel(h); }`;

/** The air's density at a height over its density at height 0 (an isothermal air, as the flight's). */
export const airDensity = (height, scaleHeight = 8500) => Math.exp(-Math.max(height, 0) / scaleHeight);
/** An exhaust's shape by the air round it (`air`: density over sea level's, 1 .. 0 the vacuum) and the
 * afterburner (`boost` 0..1): a tapering flame with a sharp core and shock diamonds in dense air, a wide faint
 * bell in none; the core blue-white, orange-yellow with the afterburner; the diamonds further apart as the air thins. */
export function plumeShape(air = 1, boost = 0) {
  const e = 1 - Math.pow(clamp(air), 0.3), b = clamp(boost), warm = 1 - e;
  return {spread: 0.045 + 0.6 * e * e, length: (9 - 1.5 * e) * (1 + 0.55 * b), diamonds: warm * warm * (0.55 + 0.45 * b), spacing: (1.7 + 2.6 * e) * (1 + 0.25 * b),
    gain: mix(0.5, 1, warm) * (1 + 0.5 * b), coreLength: mix(2.5, 6.5, warm) * (1 + 0.5 * b), coreRadius: mix(0.5, 0.42, warm), taper: warm * warm, outer: mix(0.4, 0.26, warm) * (1 + 0.25 * b),
    core: [mix(0.62, 1.0, b) * mix(1.15, 1, warm), mix(0.78, 0.72, b), mix(1.0, 0.3, b)], edge: [mix(0.3, 1.0, warm), mix(0.42, 0.42 + 0.1 * b, warm), mix(1.0, 0.1, warm)]};
}
/** How much of a vapour cone a Mach number shows (0..1): all of it at Mach 0.97, a tenth 0.04 away, and only in
 * dense (low, humid) air. */
export const coneLevel = (mach, air = 1) => { const m = (mach - 0.97) / 0.026; return Math.exp(-m * m) * smooth(0.4, 0.8, air); };
/** How much vapour a turn pulls over the wings (0..1): from about 2.5 g, all of it at 5, only in dense air. */
export const wingVapour = (load, air = 1) => smooth(2.4, 5, Math.abs(load)) * smooth(0.2, 0.65, air);
/** The heights contrails form in ([from, full] metres over the sphere): none below, all of them above. */
export const CONTRAIL_BAND = Object.freeze([8000, 9000]);
export const contrailLevel = (height, band = CONTRAIL_BAND) => smooth(band[0], band[1], height);

/** The birth times of a trail's rings at time `now`: `now` itself, then multiples of `step` for `per` rings,
 * of 2 step for the next `per`, of 4 step ... back to `now - life`. A ring's time is a fixed multiple, so the
 * place it marks does not move from frame to frame; older stretches are marked more sparsely. */
export function trailTimes(now, {life = 60, step = 1 / 30, per = 24} = {}) {
  const out = [now];
  let young = 0;
  for (let level = 0; young < life && level < 24; level++) {
    const d = step * 2 ** level, old = Math.min(life, young + per * d);
    for (let m = Math.ceil((now - young) / d - 1e-9) - 1; m * d > now - old - 1e-9; m--) if (m * d < out[out.length - 1] - 1e-9) out.push(m * d);
    young = old;
  }
  return out;
}
/** The kinds of trail: `life` (seconds), radius = start + grow age^0.75 (metres, times the trail's `size`),
 * `rise`/`fade` (the shares of the life it takes to appear and over which it thins), `wave` (the slow snaking
 * of an old trail, in radii), `lumps`, `gap` (seconds before the vapour shows behind the engine). Looks. */
export const TRAILS = Object.freeze({
  contrail: Object.freeze({life: 70, start: 1.2, grow: 2.2, rise: 0.004, fade: 0.75, wave: 0.9, lumps: 0.55, gap: 0.12, density: 0.9, step: 1 / 30}),
  tip: Object.freeze({life: 1.6, start: 0.16, grow: 0.5, rise: 0.02, fade: 0.9, wave: 0.0, lumps: 0.25, gap: 0, density: 0.75, step: 1 / 60}),
  plasma: Object.freeze({life: 5, start: 0.7, grow: 0.5, rise: 0.01, fade: 1.0, wave: 0.25, lumps: 0.5, gap: 0, density: 1, step: 1 / 60}),
});
export const trailRadius = (age, kind, size = 1) => size * (kind.start + kind.grow * Math.pow(Math.max(age, 0), 0.75));
export const trailAlpha = (age, kind) => (age < kind.gap || age >= kind.life ? 0 : smooth(kind.gap, kind.gap + kind.rise * kind.life, age) * Math.pow(1 - smooth((1 - kind.fade) * kind.life, kind.life, age), 1.5));

/** A flight read at any flight time: `tracker(ctx.flight, "Plane")` → {now(t), at(tau)}. now(t): the frame of
 * scene time t ({time, position, velocity, quaternion, heating, mach, load, height, aboveGround}); at(tau): the
 * same at flight second tau, between frames by straight lines, before the scene's first frame straight back
 * along that frame's velocity (the flight before the scene is not in the data). */
export function tracker(flight, name) {
  if (!flight || typeof flight.series !== "function") throw fail("flight: give ctx.flight (a scene with flight_data:)");
  const names = flight.names ?? [];
  if (!names.includes(name)) throw fail(`no flight "${name}"${hint(name, names)}; flights: ${names.join(", ")}`);
  const s = flight.series(name), fps = flight.fps, last = flight.frames - 1, rate = fps / (flight.speedup ?? 1);
  let first = 0;
  while (first < last && s.time[first] < 0) first++;
  const t0 = s.time[first];
  const read = (k) => ({time: s.time[k], position: [s.position[3 * k], s.position[3 * k + 1], s.position[3 * k + 2]], velocity: [s.velocity[3 * k], s.velocity[3 * k + 1], s.velocity[3 * k + 2]],
    quaternion: [s.quaternion[4 * k], s.quaternion[4 * k + 1], s.quaternion[4 * k + 2], s.quaternion[4 * k + 3]], heating: s.heating[k], mach: s.mach[k], load: s.load[k], height: s.height[k], aboveGround: s.above_ground[k]});
  return {
    name, speedup: flight.speedup ?? 1,
    now: (t) => read(clamp(Math.round(t * fps), 0, last)),
    at(tau) {
      if (tau <= t0) { const a = read(first), d = tau - t0; a.time = tau; a.position = a.position.map((p, i) => p + a.velocity[i] * d); return a; }
      const x = Math.min(first + (tau - t0) * rate, last), k = Math.min(Math.floor(x), last - 1 < first ? first : last - 1), u = x - k, a = read(k);
      if (u <= 0 || k >= last) return a;
      const b = read(k + 1), dot = a.quaternion.reduce((sum, q, i) => sum + q * b.quaternion[i], 0), sign = dot < 0 ? -1 : 1;
      const q = a.quaternion.map((v, i) => mix(v, sign * b.quaternion[i], u)), n = Math.hypot(...q) || 1;
      const out = {time: tau, position: a.position.map((v, i) => mix(v, b.position[i], u)), velocity: a.velocity.map((v, i) => mix(v, b.velocity[i], u)), quaternion: q.map((v) => v / n)};
      for (const key of ["heating", "mach", "load", "height", "aboveGround"]) out[key] = mix(a[key], b[key], u);
      return out;
    },
  };
}
/** Spark `i` at time t: {born, age (0..1 of its life), life (seconds), a, b, c (three numbers 0..1 for its
 * place and drift)}: each spark lives again and again, each life from its own numbers. */
export function sparkAt(i, t, seed = 1) {
  const life = 0.22 + 0.5 * hash(i, 1, seed), x = t / life + hash(i, 2, seed), cycle = Math.floor(x);
  return {born: (cycle - hash(i, 2, seed)) * life, age: x - cycle, life, a: hash(i, 3 + 7 * cycle, seed), b: hash(i, 4 + 7 * cycle, seed), c: hash(i, 5 + 7 * cycle, seed)};
}
/** How an effect's light flickers at t (fixed sines round 1; `i` tells effects apart). */
export const flicker = (t, i = 0) => 1 + 0.06 * Math.sin(TAU * 13.1 * t + i * 2.1) + 0.04 * Math.sin(TAU * 29.3 * t + i * 4.3) + 0.04 * Math.sin(TAU * 5.3 * t + i);

export const QUALITIES = Object.freeze({
  fast: Object.freeze({sides: 6, per: 14, sparks: 14, skin: true, layer: 8, map: 64}),
  standard: Object.freeze({sides: 8, per: 24, sparks: 36, skin: true, layer: 14, map: 192}),
  fine: Object.freeze({sides: 12, per: 36, sparks: 72, skin: true, layer: 24, map: 256}),
});

// ---------- shaders ----------
// every material draws itself: to the canvas in display values (light as a screen blend, so layers of glow
// roll off towards white instead of clipping; vapour laid over), into a target (three-finish) as linear light
const OUT_GLSL = `${DISPLAY_GLSL}
uniform vec2 uOut;   // 1: to the canvas; the renderer's exposure
uniform float uLevel;
vec4 glowOut(vec3 light) { light *= uOut.y * uLevel; return vec4(uOut.x > 0.5 ? display(light) : light, 1.0); }
vec4 vapourOut(vec3 colour, float alpha) { colour *= uOut.y; return vec4((uOut.x > 0.5 ? display(colour) : colour) * alpha, alpha); }`;
const NOISE_GLSL = `float hash21(vec2 p) { vec3 q = fract(vec3(p.xyx) * 0.1031); q += dot(q, q.yzx + 33.33); return fract((q.x + q.y) * q.z); }
float vnoise(vec2 p) { vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash21(i), hash21(i + vec2(1.0, 0.0)), f.x), mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0, 1.0)), f.x), f.y); }`;
function tune(material, glow) {
  material.toneMapped = false; material.depthWrite = false; material.transparent = true; material.fog = false; material.forceSinglePass = true;
  material.blending = THREE.CustomBlending; material.blendEquation = THREE.AddEquation;
  material.blendSrc = THREE.OneFactor; material.blendDst = glow ? THREE.OneFactor : THREE.OneMinusSrcAlphaFactor;
  material.blendSrcAlpha = glow ? THREE.ZeroFactor : THREE.OneFactor; material.blendDstAlpha = glow ? THREE.OneFactor : THREE.OneMinusSrcAlphaFactor;
  material.uniforms.uOut = {value: new THREE.Vector2(0, 1)}; material.uniforms.uLevel = {value: 1};
  material.userData.glow = glow;
  return material;
}
// before each draw: where the picture goes, the pixel's size, and whatever of the camera the thing needs
function watch(mesh, extra = null) {
  mesh.frustumCulled = false;
  mesh.onBeforeRender = (renderer, scene, camera) => {
    const m = mesh.material, canvas = renderer.getRenderTarget() === null;
    m.uniforms.uOut.value.set(canvas ? 1 : 0, renderer.toneMapping === THREE.NoToneMapping ? 1 : renderer.toneMappingExposure);
    if (m.userData.glow) m.blendSrc = canvas ? THREE.OneMinusDstColorFactor : THREE.OneFactor;
    if (m.uniforms.uView) { const size = renderer.getCurrentViewport(new THREE.Vector4()); m.uniforms.uView.value.y = 2 / (camera.projectionMatrix.elements[5] * Math.max(size.w, 1)); }
    if (extra) extra(renderer, camera);
    m.uniformsNeedUpdate = true;
  };
  return mesh;
}

// a trail: a soft tube round a line of rings (vapour lit by the sun and the sky, or light of its own)
const TRAIL_VERT = `
attribute vec3 aDir; attribute vec4 aData; attribute vec3 aColor;
uniform vec4 uView;   // the least radius in pixels, a pixel's angle, the light kept when widened, -
varying vec3 vN; varying vec3 vTo; varying vec4 vData; varying vec3 vColor; varying float vKeep;
void main() {
  vec4 c = modelViewMatrix * vec4(position, 1.0);
  float wide = max(aData.x, uView.x * uView.y * length(c.xyz));
  vKeep = max(aData.x / max(wide, 1e-6), uView.z);
  vec4 world = modelMatrix * vec4(position + aDir * wide, 1.0);
  vN = normalize(mat3(modelMatrix) * aDir); vTo = world.xyz - cameraPosition; vData = aData; vColor = aColor;
  gl_Position = projectionMatrix * viewMatrix * world;
}`;
const TRAIL_FRAG = (air) => `
precision highp float;
${air ? AIR_GLSL : ""}
${OUT_GLSL}
${NOISE_GLSL}
varying vec3 vN; varying vec3 vTo; varying vec4 vData; varying vec3 vColor; varying float vKeep;
uniform vec3 uSunDir, uSun, uSky; uniform vec4 uLook;   // softness, lumps, the lumps' length along the trail, time
void main() {
  vec3 n = normalize(vN), rd = normalize(vTo);
  float facing = abs(dot(n, rd)), along = vData.z * uLook.z, turn = vData.w * 6.2831853;
  float lump = vnoise(vec2(along + 0.8 * cos(turn), 0.8 * sin(turn) + along * 0.37)) * 0.65 + vnoise(vec2(along * 3.1 - 1.2 * sin(turn), 1.2 * cos(turn) + 5.0)) * 0.35;
  float alpha = vData.y * pow(facing, uLook.x) * mix(1.0, smoothstep(0.12, 0.8, lump) * 1.5, uLook.y);
  #ifdef GLOW
    gl_FragColor = glowOut(vColor * alpha * vKeep * (0.85 + 0.3 * lump));
  #else
    alpha = clamp(alpha * vKeep, 0.0, 0.97);
    float lit = 0.5 + 0.5 * dot(n, uSunDir), ahead = pow(max(dot(rd, uSunDir), 0.0), 6.0);
    vec3 colour = vColor * (uSun * (0.4 + 0.52 * lit + 1.2 * ahead * (1.0 - alpha)) + uSky * 1.3);
    ${air ? "colour = airThrough(colour, vTo);" : ""}
    gl_FragColor = vapourOut(colour, alpha);
  #endif
}`;

// the shock layer: the air just upwind of the craft's windward surfaces. The craft is drawn once, seen from
// upwind, into a small map (how far upwind its surface reaches, how squarely it faces the flow); a view ray
// then sums a layer whose light falls off with the distance upwind of that surface: between two samples the
// distance is taken as a straight line, so the sum is exact however thin the layer (no bands). The sum is
// drawn on a ball round the craft where the ray misses the craft, and on the craft's own surfaces (to the
// surface and no further) where it hits: the craft hides what is behind it and nothing shines through.
const MAP_VERT = `
uniform vec3 uWind, uCentre;
varying vec2 vMap;
void main() { vec4 at = modelMatrix * vec4(position, 1.0); vMap = vec2(dot(at.xyz - uCentre, uWind), max(dot(normalize(mat3(modelMatrix) * normal), uWind), 0.0)); gl_Position = projectionMatrix * viewMatrix * at; }`;
const MAP_FRAG = "precision highp float; varying vec2 vMap; void main() { gl_FragColor = vec4(vMap, 0.0, 1.0); }";
const LAYER_GLSL = `
uniform sampler2D uMap; uniform mat3 uFrame; uniform vec3 uCentre;
uniform vec4 uLayer;   // the map's half width (metres), the layer's thickness (metres), the radius the layer is summed in, the ball's radius
uniform vec4 uNow;     // heating, time, -, -
vec3 mapAt(vec3 p, float lod) {   // the distance upwind of the windward surface, its facing, how much surface is there
  vec2 uv = p.xy / (2.0 * uLayer.x) + 0.5;
  vec4 m = textureLod(uMap, uv, lod) * step(abs(uv.x - 0.5), 0.5) * step(abs(uv.y - 0.5), 0.5);
  return m.a > 0.004 ? vec3(p.z - m.r / m.a, m.g / m.a, m.a) : vec3(1e4, 0.0, 0.0);
}
float piece(float s0, float s1, float dt, float thick) {   // the layer's light along a step on which the distance runs from s0 to s1
  float e0 = exp(-max(s0, 0.0) / thick), e1 = exp(-max(s1, 0.0) / thick), ds = s1 - s0;
  return abs(ds) > 1e-3 * thick ? dt * (e0 - e1) / ds : dt / thick * e0 * step(0.0, s0);
}
// the layer's light on the view ray from the camera at o along d (the craft's axes), no further than reach
vec3 layerLight(vec3 o, vec3 d, float reach) {
  vec3 oc = o - uCentre;
  float b = dot(oc, d), c = dot(oc, oc) - uLayer.z * uLayer.z, h = b * b - c;
  if (h <= 0.0) return vec3(0.0);
  h = sqrt(h);
  float t0 = max(-b - h, 0.0), t1 = min(-b + h, reach);
  if (t1 <= t0) return vec3(0.0);
  mat3 back = transpose(uFrame);
  vec3 po = back * oc, pd = back * d;
  float dt = (t1 - t0) / float(STEPS), thick = uLayer.y;
  vec3 m0 = mapAt(po + pd * t0, 0.6);
  float amount = 0.0, heat = 0.0;
  for (int i = 1; i <= STEPS; i++) {
    vec3 p = po + pd * (t0 + dt * float(i)), m1 = mapAt(p, 0.6);
    // where one end of the step has no surface under it, the other end's distance stands for both
    // (at the very outline the map's distance comes from a single texel, in blocks: the layer ends just before)
    float f0 = pow(m0.y, 0.7) * smoothstep(0.55, 1.0, m0.z), f1 = pow(m1.y, 0.7) * smoothstep(0.55, 1.0, m1.z), a = piece(m0.z > 0.0 ? m0.x : m1.x, m1.z > 0.0 ? m1.x : m0.x, dt, thick) * 0.5 * (f0 + f1);
    amount += a; heat += a * 0.5 * (m0.y + m1.y);
    m0 = m1;
  }
  float face = amount > 1e-5 ? heat / amount : 0.0;
  vec3 at = po + pd * 0.5 * (t0 + t1);
  float streak = vnoise(vec2(at.x * 0.9 + at.y * 0.5, (at.z + uNow.y * 70.0) * 0.12)) * 0.6 + vnoise(vec2(at.x * 2.3 - at.y, (at.z + uNow.y * 110.0) * 0.3)) * 0.4;
  return heatLight(uNow.x * (0.34 + 0.66 * face * face) * (0.85 + 0.3 * streak)) * (1.0 - exp(-1.1 * amount));
}`;
const BALL_VERT = `
uniform vec3 uCentre; uniform vec4 uLayer;
varying vec3 vLocal; varying vec3 vCam;
void main() { vLocal = position * uLayer.w * 1.02 + uCentre; vCam = (inverse(modelMatrix) * vec4(cameraPosition, 1.0)).xyz; gl_Position = projectionMatrix * modelViewMatrix * vec4(vLocal, 1.0); }`;
const BALL_FRAG = `
precision highp float;
${OUT_GLSL}
${HEAT_GLSL}
${NOISE_GLSL}
${LAYER_GLSL}
varying vec3 vLocal; varying vec3 vCam;
uniform vec3 uRadii, uWind;
void main() {
  // and a soft glow round the windward side: a ball of light summed in closed form (the bloom of the layer)
  vec3 rd = normalize(vLocal - vCam), o = (vCam - uCentre - uWind * uLayer.x * 0.22) / (uRadii * 0.95), d = rd / (uRadii * 0.95);
  float dd = dot(d, d), od = dot(o, d), k = 2.6, sum = sqrt(3.14159 / (k * dd)) * exp(-k * max(dot(o, o) - od * od / dd, 0.0));
  float bloom = 1.0 - exp(-sum / uLayer.x * 0.9);
  gl_FragColor = glowOut(layerLight(vCam, rd, 1e9) + heatLight(uNow.x * 0.5) * bloom * 0.3);
}`;

// the wake: two soft streams behind the craft along the flow, each summed in closed form where the view ray
// passes nearest its axis (no steps, so no bands); streaks run down it with the time
const WAKE_VERT = `
uniform vec4 uBox;   // the bound's radius, its length behind, ahead, -
uniform mat3 uFrame; uniform vec3 uCentre;
varying vec3 vLocal; varying vec3 vCam;
void main() { vec3 p = vec3(position.xy * uBox.x, mix(uBox.z, -uBox.y, position.z)); vLocal = uFrame * p + uCentre; vCam = (inverse(modelMatrix) * vec4(cameraPosition, 1.0)).xyz; gl_Position = projectionMatrix * modelViewMatrix * vec4(vLocal, 1.0); }`;
const WAKE_FRAG = `
precision highp float;
${OUT_GLSL}
${HEAT_GLSL}
${NOISE_GLSL}
varying vec3 vLocal; varying vec3 vCam;
uniform mat3 uFrame; uniform vec3 uCentre; uniform vec4 uNow; uniform vec4 uWake;   // uNow: heating, time, -, -; uWake: radius across, radius up, length, the body's length
vec3 stream(vec3 o, vec3 d, float wide, float len, float heat, float speed) {
  // the frame's z is the wind (the way the craft goes): the stream runs along -z; x and y are scaled to a round stream
  vec2 scale = uWake.xy * wide;
  vec3 so = vec3(o.xy / scale, o.z), sd = vec3(d.xy / scale, d.z);
  float a = dot(sd.xy, sd.xy), t = a > 1e-9 ? max(-dot(so.xy, sd.xy) / a, 0.0) : 0.0;
  vec3 p = so + sd * t;
  float s = -p.z, grow = (1.0 + 0.35 * max(s, 0.0) / len) * (1.0 - 0.3 * exp(-max(s, 0.0) / (0.6 * uWake.w)) * smoothstep(0.0, 0.4 * uWake.w, s));
  float r2 = dot(p.xy, p.xy) / (grow * grow);
  float chord = 1.7725 * grow / max(sqrt(a), 0.22 / max(scale.x, scale.y));
  float begin = smoothstep(-0.1 * uWake.w, 0.6 * uWake.w, s), fade = exp(-max(s, 0.0) / len) * (1.0 - smoothstep(2.2 * len, 3.0 * len, s));
  float run = (s + uNow.y * speed) / uWake.w;
  float streaks = vnoise(vec2(p.x * 2.3 + p.y * 1.1, run * 2.2)) * 0.6 + vnoise(vec2(p.x * 5.0 - p.y * 2.0 + 3.0, run * 5.5)) * 0.4;
  float h = heat * (0.25 + 0.6 * fade * fade) * (0.7 + 0.6 * streaks) * exp(-r2 * 0.8);
  return heatLight(h) * exp(-r2 * 1.6) * begin * fade * chord / max(scale.x, scale.y) * (0.6 + 0.8 * streaks);
}
void main() {
  mat3 back = transpose(uFrame);
  vec3 o = back * (vCam - uCentre), d = back * normalize(vLocal - vCam);
  vec3 light = stream(o, d, 0.4, uWake.z * 0.3, uNow.x, uWake.w * 9.0) * 0.3 + stream(o, d, 0.85, uWake.z, uNow.x * 0.8, uWake.w * 5.0) * 0.12;
  gl_FragColor = glowOut(light);
}`;

// hot surfaces: the craft's own meshes drawn once more, glowing where they face the flow, lit a little by the
// shock layer where they do not
const SKIN_VERT = `
varying vec3 vN; varying vec3 vAt; varying vec3 vLocal; varying vec3 vCam;
uniform mat4 uToCraft;   // from the scene to the craft's axes
void main() {
  vec4 world = modelMatrix * vec4(position, 1.0);
  vN = normalize(mat3(modelMatrix) * normal); vAt = position; vLocal = (uToCraft * world).xyz; vCam = (uToCraft * vec4(cameraPosition, 1.0)).xyz;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;
const SKIN_FRAG = `
precision highp float;
${OUT_GLSL}
${HEAT_GLSL}
${NOISE_GLSL}
${LAYER_GLSL}
varying vec3 vN; varying vec3 vAt; varying vec3 vLocal; varying vec3 vCam;
uniform vec3 uWind;
void main() {
  vec3 n = normalize(vN);
  float wind = dot(n, uWind), face = pow(max(wind, 0.0), 1.6), spill = max(wind + 0.75, 0.0) / 1.75;
  float mottle = 0.8 + 0.4 * vnoise(vAt.xz * 2.3 + vAt.y * 1.7);
  vec3 light = heatLight(uNow.x * (0.3 + 0.7 * face) * mottle) * face * 0.5 + heatLight(uNow.x * 0.6) * spill * spill * 0.07;
  light *= 0.94 + 0.06 * sin(uNow.y * 71.0 + vAt.z * 3.0);
  #ifdef LAYER
    light += layerLight(vCam, normalize(vLocal - vCam), length(vLocal - vCam));
  #endif
  gl_FragColor = glowOut(light);
}`;

// sparks and the far head: points of light
const POINT_VERT = `
attribute vec4 aLook;   // radius (metres), brightness, heat, -
uniform vec4 uView;     // the least radius in pixels, a pixel's angle, the light kept when shown larger, 1: fades when near (the far head)
varying vec2 vLook; varying float vKeep;
void main() {
  vec4 c = modelViewMatrix * vec4(position, 1.0);
  float px = aLook.x / (uView.y * max(-c.z, 1e-3)), shown = max(px, uView.x);
  vKeep = min(1.0, (px * px) / (shown * shown) + uView.z) * (1.0 - uView.w * smoothstep(6.0, 40.0, px)); vLook = aLook.yz;
  gl_PointSize = 2.0 * shown; gl_Position = projectionMatrix * c;
}`;
const POINT_FRAG = `
precision highp float;
${OUT_GLSL}
${HEAT_GLSL}
varying vec2 vLook; varying float vKeep;
void main() {
  vec2 p = gl_PointCoord * 2.0 - 1.0; float r2 = dot(p, p);
  if (r2 > 1.0) discard;
  float soft = exp(-r2 * 4.5) - 0.011;
  #ifdef HEAD
    soft = exp(-r2 * 16.0) + 0.22 * exp(-r2 * 3.5) * (1.0 - r2);
  #endif
  gl_FragColor = glowOut(heatColor(vLook.y) * vLook.x * max(soft, 0.0) * vKeep);
}`;

// vapour over a wing: a soft ball of mist summed along the view ray in closed form
const MIST_VERT = `
varying vec3 vWorld; varying vec3 vCam;
void main() { vec4 w = modelMatrix * vec4(position, 1.0); vWorld = w.xyz; vCam = (inverse(modelMatrix) * vec4(cameraPosition, 1.0)).xyz; gl_Position = projectionMatrix * viewMatrix * w; }`;
const MIST_FRAG = `
precision highp float;
${OUT_GLSL}
${NOISE_GLSL}
varying vec3 vWorld; varying vec3 vCam;
uniform mat3 uBack; uniform vec3 uSunDir, uSun, uSky; uniform vec2 uMist;   // density (1 / metre), a number that tells the mists apart and moves their unevenness
void main() {
  vec3 rd = normalize(vWorld - cameraPosition), d = uBack * rd, o = vCam;
  float dd = dot(d, d), od = dot(o, d), k = 6.76;
  vec3 near = o - d * (od / dd);
  float uneven = 0.25 + 1.5 * vnoise(near.xy * 2.6 + near.z * 1.7 + uMist.y) * vnoise(near.yx * 5.3 + uMist.y * 1.3 + 7.0) + 0.5 * vnoise(near.xy * 9.0 - uMist.y);
  float sum = sqrt(3.14159 / (k * dd)) * exp(-k * max(dot(o, o) - od * od / dd, 0.0));
  float alpha = 1.0 - exp(-uMist.x * sum * uneven);
  float ahead = pow(max(dot(rd, uSunDir), 0.0), 6.0);
  gl_FragColor = vapourOut(uSun * (0.72 + 0.9 * ahead * (1.0 - alpha)) + uSky * 1.3, alpha * 0.92);
}`;

// engine exhaust in air: a flame of two parts, each summed in closed form where the view ray passes nearest
// the flame's axis (no steps: the core's edge stays sharp): an inner core leaving the bell, a translucent
// outer flame that tapers in dense air and opens to a wide faint bell in thin air, and along the axis a row
// of shock diamonds, evenly spaced, each smaller and dimmer than the one before
const EXHAUST_VERT = `
uniform vec4 uShape;   // exit radius, spread, length (exit radii to 1/e), bound radius
varying vec3 vPos; varying vec3 vCam;
void main() {
  float s = -position.y, Re = uShape.x;
  vPos = vec3(position.x * mix(1.3 * Re, uShape.w, s), mix(1.0 * Re, -uShape.z * REACH * Re, s), position.z * mix(1.3 * Re, uShape.w, s));
  vCam = (inverse(modelMatrix) * vec4(cameraPosition, 1.0)).xyz; gl_Position = projectionMatrix * modelViewMatrix * vec4(vPos, 1.0);
}`;
const EXHAUST_FRAG = `
precision highp float;
${OUT_GLSL}
${NOISE_GLSL}
varying vec3 vPos; varying vec3 vCam;
uniform vec3 uCore, uEdge; uniform vec4 uShape;
uniform vec4 uNow;    // power, time, diamonds, the core's length (exit radii)
uniform vec4 uMore;   // the diamonds' spacing (exit radii), the core's radius, how much the outer flame tapers, its brightness
void main() {
  vec3 o = vCam / uShape.x, d = normalize(vPos - vCam);
  float a = dot(d.xz, d.xz), t = a > 1e-6 ? max(-dot(o.xz, d.xz) / a, 0.0) : 0.0;
  vec3 p = o + d * t;
  float s = -p.y, r = length(p.xz), across = 1.0 / max(sqrt(a), 0.2), power = min(uNow.x, 1.0);
  float len = uShape.z * (0.3 + 0.7 * power), begin = smoothstep(-0.4, 0.15, s);
  // the outer flame
  float taper = 1.0 - uMore.z * smoothstep(0.15 * len, 1.9 * len, s);
  float ro = 0.95 * (1.0 + uShape.y * max(s, 0.0)) * max(taper, 0.04);
  float lick = 0.86 + 0.28 * vnoise(vec2(s * 0.9 - uNow.y * 34.0, r * 2.0 + 3.0));
  float outer = exp(-r * r / (ro * ro)) * exp(-max(s, 0.0) / len) * (1.0 - smoothstep(1.9 * len, 2.35 * len, s)) * begin * across * lick / (1.0 + 0.35 * uShape.y * max(s, 0.0));
  // the core: a sharp-edged spike
  float lc = uNow.w * (0.3 + 0.7 * power), u = clamp(s / lc, 0.0, 1.0), rc = uMore.y * pow(1.0 - u, 0.75) * (1.0 + 0.04 * sin(uNow.y * 53.0));
  float core = s < lc ? smoothstep(rc, rc * 0.72, r) * (0.6 + 0.4 * sqrt(max(1.0 - r * r / max(rc * rc, 1e-6), 0.0))) * begin * min(across, 2.5) : 0.0;
  // the diamonds: lozenges on the axis, every uMore.x radii
  float phase = s / uMore.x - 0.3, cell = floor(phase), x = abs(fract(phase) - 0.5) * 2.0;
  float size = uMore.y * 1.15 * exp(-0.17 * cell), lozenge = cell >= 0.0 ? smoothstep(1.0, 0.45, r / size + x * 1.05) * exp(-0.4 * cell) * (1.0 - smoothstep(0.9 * len, 1.5 * len, s)) * min(across, 2.5) : 0.0;
  vec3 light = uEdge * (outer * uMore.w) + uCore * (core * 1.5 + lozenge * uNow.z * 2.2) + vec3(lozenge * lozenge * uNow.z * 0.4);
  gl_FragColor = glowOut(light * uNow.x);
}`;
const EXHAUST_REACH = 2.4;

// the craft's solid meshes (what a hot surface or the windward map is drawn from)
function solids(object) {
  const found = [];
  object.traverse((mesh) => { if (mesh.isMesh && !mesh.userData.keep && mesh.material && mesh.material.isMeshStandardMaterial && !mesh.material.transparent && mesh.geometry.attributes.normal) found.push(mesh); });
  return found;
}
// ---------- the windward map: the craft seen from upwind, drawn again only when the wind's direction in the craft's axes changes ----------
class WindMap {
  constructor(object, shape, size) {
    this.object = object; this.half = Math.hypot(...shape.radii) * 1.12; this.centre = V3(...shape.center);
    this.target = new THREE.WebGLRenderTarget(size, size, {type: THREE.HalfFloatType, format: THREE.RGBAFormat, minFilter: THREE.LinearMipmapLinearFilter, magFilter: THREE.LinearFilter, generateMipmaps: true, depthBuffer: true});
    this.material = new THREE.ShaderMaterial({vertexShader: MAP_VERT, fragmentShader: MAP_FRAG, side: THREE.DoubleSide, uniforms: {uWind: {value: V3(0, 0, 1)}, uCentre: {value: this.centre}}});
    this.scene = new THREE.Scene(); this.scene.matrixWorldAutoUpdate = false;
    this.camera = new THREE.OrthographicCamera(-this.half, this.half, this.half, -this.half, 0.01 * this.half, 3 * this.half); this.camera.matrixAutoUpdate = false; this.camera.matrixWorldAutoUpdate = false;
    this.proxies = solids(object).map((mesh) => { const proxy = new THREE.Mesh(mesh.geometry, this.material); proxy.matrixAutoUpdate = false; proxy.frustumCulled = false; proxy.userData.of = mesh; this.scene.add(proxy); return proxy; });
    this.key = null; this.drawn = null; this.draws = 0; this._back = new THREE.Matrix4();
  }
  aim(x, y, wind) {
    this.camera.matrixWorld.makeBasis(x, y, wind).setPosition(this.centre.clone().addScaledVector(wind, 1.5 * this.half)); this.camera.matrixWorldInverse.copy(this.camera.matrixWorld).invert();
    this.material.uniforms.uWind.value.copy(wind);
    this.key = [wind.x, wind.y, wind.z].map((v) => v.toFixed(4)).join(",");
  }
  draw(renderer) {
    if (this.key === this.drawn) return;
    this.drawn = this.key; this.draws++;
    this.object.updateMatrixWorld(true); this._back.copy(this.object.matrixWorld).invert();
    for (const proxy of this.proxies) proxy.matrixWorld.multiplyMatrices(this._back, proxy.userData.of.matrixWorld);
    const before = renderer.getRenderTarget(), auto = renderer.autoClear, shadows = renderer.shadowMap.autoUpdate, colour = renderer.getClearColor(new THREE.Color()), alpha = renderer.getClearAlpha();
    renderer.shadowMap.autoUpdate = false; renderer.autoClear = true; renderer.setClearColor(0x000000, 0);
    renderer.setRenderTarget(this.target); renderer.state.buffers.depth.setMask(true); renderer.clear(); renderer.render(this.scene, this.camera);
    renderer.setRenderTarget(before); renderer.setClearColor(colour, alpha); renderer.autoClear = auto; renderer.shadowMap.autoUpdate = shadows;
  }
  dispose() { this.target.dispose(); this.material.dispose(); }
}

// ---------- a trail's mesh ----------
class Tube {
  constructor(rings, sides, {glow = false, sky = null, soft = 1.4, lumps = 0.5, grain = 0.05, least = 0, keep = 0} = {}) {
    this.rings = rings; this.sides = sides;
    const n = rings * (sides + 1), g = new THREE.BufferGeometry();
    for (const [name, size] of [["position", 3], ["aDir", 3], ["aData", 4], ["aColor", 3]]) { const a = new THREE.BufferAttribute(new Float32Array(n * size), size); a.setUsage(THREE.DynamicDrawUsage); g.setAttribute(name, a); }
    const index = [];
    for (let i = 0; i < rings - 1; i++) for (let j = 0; j < sides; j++) { const a = i * (sides + 1) + j, b = a + sides + 1; index.push(a, b, a + 1, a + 1, b, b + 1); }
    g.setIndex(index); g.setDrawRange(0, 0);
    const air = !glow && !!sky;
    this.material = tune(new THREE.ShaderMaterial({vertexShader: TRAIL_VERT, fragmentShader: TRAIL_FRAG(air), defines: glow ? {GLOW: 1} : {}, side: THREE.DoubleSide,
      uniforms: {...(air ? sky.uniforms : {}), uView: {value: new THREE.Vector4(least, 0.002, keep, 0)}, uSunDir: {value: V3(0, 1, 0)}, uSun: {value: V3(1, 1, 1)}, uSky: {value: V3(0.2, 0.25, 0.3)}, uLook: {value: new THREE.Vector4(soft, lumps, grain, 0)}}}), glow);
    if (air && typeof sky.shadowsInto === "function") sky.shadowsInto(this.material);      // the air's shadows in front of the trail (vidgen/space-air)
    this.mesh = watch(new THREE.Mesh(g, this.material)); this.mesh.renderOrder = glow ? 6 : 4; this.mesh.name = glow ? "trail of light" : "vapour trail";
    this._t = V3(); this._a = V3(); this._b = V3();
  }
  /** Lay the tube through `points` ([{p: [x, y, z], tangent: [x, y, z], radius, alpha, along, color}], head first), in `origin`'s frame of reference (the mesh stands at `origin`: small numbers on the GPU). */
  lay(points, origin, turn = null) {
    const g = this.mesh.geometry, P = g.attributes.position.array, D = g.attributes.aDir.array, A = g.attributes.aData.array, C = g.attributes.aColor.array, S = this.sides, count = Math.min(points.length, this.rings);
    for (let i = 0; i < count; i++) {
      const q = points[i], t = this._t.set(...q.tangent).normalize(), a = this._a.set(0, 1, 0);
      if (Math.abs(t.y) > 0.98) a.set(1, 0, 0);
      a.cross(t).normalize(); const b = this._b.copy(t).cross(a);
      for (let j = 0; j <= S; j++) {
        const k = i * (S + 1) + j, ang = TAU * j / S, ca = Math.cos(ang), sa = Math.sin(ang);
        P[3 * k] = q.p[0] - origin[0]; P[3 * k + 1] = q.p[1] - origin[1]; P[3 * k + 2] = q.p[2] - origin[2];
        D[3 * k] = a.x * ca + b.x * sa; D[3 * k + 1] = a.y * ca + b.y * sa; D[3 * k + 2] = a.z * ca + b.z * sa;
        A[4 * k] = q.radius; A[4 * k + 1] = q.alpha; A[4 * k + 2] = q.along; A[4 * k + 3] = j / S;
        C[3 * k] = q.color[0]; C[3 * k + 1] = q.color[1]; C[3 * k + 2] = q.color[2];
      }
    }
    for (const a of Object.values(g.attributes)) a.needsUpdate = true;
    g.setDrawRange(0, Math.max(count - 1, 0) * S * 6);
    if (!turn) this.mesh.position.set(...origin);
    this.mesh.visible = count > 1;
  }
}

// ---------- the effects of one craft ----------
const OPTION_KEYS = ["flight", "name", "sky", "seed", "quality", "shape", "anchors", "scaleHeight", "path", "sun", "light", "ambient", "reentry", "contrails", "exhaust", "vapour"];
const REENTRY_KEYS = ["full", "level", "shock", "skin", "wake", "sparks", "trail", "head", "thickness", "length", "persist"];
const CONTRAIL_KEYS = ["from", "band", "always", "life", "size", "level", "color"];
const EXHAUST_KEYS = ["nozzles", "level", "air"];
const VAPOUR_KEYS = ["cone", "wings", "tips", "level"];
const UPDATE_KEYS = ["velocity", "heating", "mach", "load", "height", "aboveGround", "air", "throttle", "boost", "pulse", "sun"];
const group = (where, value, keys, defaults) => (value === true ? {...defaults} : value ? {...defaults, ...known(where, value, keys)} : null);
const value = (v, t) => (typeof v === "function" ? v(t) : v);
const vec = (v) => (Array.isArray(v) ? v : v && v.isVector3 ? [v.x, v.y, v.z] : null);

/** The effects of one craft (see effects()). `object`: the things laid in the world (add it to the scene);
 * the things that ride with the craft are added to the craft's own object. `state`: the numbers of the last
 * update. `parts`: what was built ({shock, wake, skins, sparks, head, train, contrails, tips, cone, mists, exhausts}). */
export class Effects {
  constructor(target, options = {}) {
    known("effects options", options, OPTION_KEYS);
    const craft = target && target.isObject3D ? {object: target} : target;
    if (!craft || !craft.object || !craft.object.isObject3D) throw fail("effects(craft, options): a craft (anything with an `object`) or an Object3D");
    const quality = options.quality ?? "standard";
    if (!(quality in QUALITIES)) throw fail(`quality: "${quality}"${hint(quality, Object.keys(QUALITIES))}; one of: ${Object.keys(QUALITIES).join(", ")}`);
    this.craft = craft; this.quality = quality; this.q = QUALITIES[quality]; this.seed = options.seed ?? craft.seed ?? 1; this.sky = options.sky ?? null;
    this.options = {scaleHeight: options.scaleHeight ?? (this.sky && this.sky.model ? this.sky.model.H : 8500), path: options.path ?? null, sun: options.sun ?? null, light: options.light ?? [1, 1, 1], ambient: options.ambient ?? [0.16, 0.2, 0.26]};
    this.track = options.flight ? tracker(options.flight, options.name ?? (options.flight.names ?? [])[0]) : null;
    if (options.name !== undefined && !options.flight) throw fail("name: a flight's name needs `flight: ctx.flight`");
    this.reentry = group("reentry", options.reentry, REENTRY_KEYS, {full: 0.65, level: 1, shock: true, skin: this.q.skin, wake: true, sparks: true, trail: true, head: true, thickness: 0.055, length: 7, persist: TRAILS.plasma.life});
    this.contrails = group("contrails", options.contrails, CONTRAIL_KEYS, {from: "nozzles", band: CONTRAIL_BAND, always: false, life: TRAILS.contrail.life, size: 1, level: 1, color: [1, 1, 1]});
    this.exhaust = group("exhaust", options.exhaust, EXHAUST_KEYS, {nozzles: null, level: 1, air: null});
    this.vapour = group("vapour", options.vapour, VAPOUR_KEYS, {cone: true, wings: true, tips: true, level: 1});
    this.anchors = {...(craft.anchors ?? {}), ...(options.anchors ? known("anchors", options.anchors, ["nose", "tail", "belly", "leadingEdges", "wingTips", "nozzles"]) : {})};
    this.shape = this._shape(options.shape);
    this.object = new THREE.Group(); this.object.name = "effects (in the world)";
    this.attached = new THREE.Group(); this.attached.name = "effects"; this.attached.userData.keep = true; craft.object.add(this.attached);
    this.parts = {shock: null, wake: null, skins: [], sparks: null, head: null, train: null, contrails: [], tips: [], cone: null, mists: [], exhausts: []};
    this.state = {};
    this._vapours = [];
    if (this.reentry) this._buildReentry();
    if (this.contrails) this._buildContrails();
    if (this.vapour) this._buildVapour();
    if (this.exhaust) this._buildExhaust();
  }

  // the bounding ellipsoid in the craft's axes: given, from a plane's anchors, or from the meshes' boxes
  _shape(given) {
    if (given) {
      known("shape", given, ["center", "radii"]);
      if (!Array.isArray(given.radii) || given.radii.length !== 3 || !given.radii.every((r) => r > 0)) throw fail("shape: radii [across, up, along] in metres, each over 0");
      return {center: (given.center ?? [0, 0, 0]).slice(), radii: given.radii.slice()};
    }
    const a = this.anchors;
    if (a.nose && a.tail && a.belly) {
      const half = 0.5 * (a.nose.p[2] - a.tail.p[2]), wide = Math.max(0.5 * (a.belly.width ?? 0), ...(a.wingTips ?? []).map((w) => Math.abs(w.p[0])), 0.1 * half), low = Math.abs(a.belly.p[1]);
      return {center: [0, 0, 0.5 * (a.nose.p[2] + a.tail.p[2])], radii: [wide, Math.max(low, 0.09 * half), half]};
    }
    const object = this.craft.object, box = new THREE.Box3(), one = new THREE.Box3(), back = new THREE.Matrix4(), m = new THREE.Matrix4();
    object.updateMatrixWorld(true); back.copy(object.matrixWorld).invert();
    object.traverse((mesh) => {
      if (!mesh.isMesh || !mesh.material || !mesh.material.isMeshStandardMaterial) return;
      if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
      box.union(one.copy(mesh.geometry.boundingBox).applyMatrix4(m.multiplyMatrices(back, mesh.matrixWorld)));
    });
    if (box.isEmpty()) throw fail("the craft has no meshes to measure: give shape: {center: [x, y, z], radii: [across, up, along]}");
    const c = box.getCenter(V3()), s = box.getSize(V3());
    return {center: [c.x, c.y, c.z], radii: [0.5 * s.x, 0.5 * s.y, 0.5 * s.z].map((r) => Math.max(r, 0.05 * s.length()))};
  }

  _buildReentry() {
    const o = this.reentry, {center, radii} = this.shape, big = Math.max(...radii), ball = new THREE.IcosahedronGeometry(1, 3);
    const layer = () => ({uMap: {value: null}, uFrame: {value: new THREE.Matrix3()}, uCentre: {value: V3(...center)}, uLayer: {value: new THREE.Vector4(1, 1, 1, 0)}, uNow: {value: new THREE.Vector4()}});
    if (o.shock) {
      this._wind = new WindMap(this.craft.object, this.shape, this.q.map);
      const material = tune(new THREE.ShaderMaterial({vertexShader: BALL_VERT, fragmentShader: BALL_FRAG, defines: {STEPS: this.q.layer}, side: THREE.BackSide, uniforms: layer()}), true);
      material.uniforms.uRadii = {value: V3(...radii)}; material.uniforms.uWind = {value: V3(0, 0, 1)};
      this.parts.shock = watch(new THREE.Mesh(ball, material), (renderer) => this._wind.draw(renderer));
      this.parts.shock.renderOrder = 7; this.attached.add(this.parts.shock);
    }
    if (o.wake) {
      const tube = new THREE.CylinderGeometry(1, 1, 1, 20, 1, false); tube.rotateX(Math.PI / 2); tube.translate(0, 0, 0.5);
      const material = tune(new THREE.ShaderMaterial({vertexShader: WAKE_VERT, fragmentShader: WAKE_FRAG, side: THREE.BackSide,
        uniforms: {uBox: {value: new THREE.Vector4(big * 3, big * 2 * o.length * 3.05, big * 0.3, 0)}, uFrame: {value: new THREE.Matrix3()}, uCentre: {value: V3(...center)}, uNow: {value: new THREE.Vector4()}, uWake: {value: new THREE.Vector4(1, 1, big * 2 * o.length, big * 2)}}}), true);
      const mesh = new THREE.Mesh(tube, material), eye = V3(), wind = V3();
      this.parts.wake = watch(mesh, (renderer, camera) => {
        // seen from behind the wake is in front of the craft, seen from ahead behind it: the side of the bound that is tested against the craft follows
        mesh.worldToLocal(eye.setFromMatrixPosition(camera.matrixWorld)).sub(material.uniforms.uCentre.value);
        const behind = eye.dot(wind.setFromMatrix3Column(material.uniforms.uFrame.value, 2)) < 0, far = Math.hypot(eye.x, eye.y, eye.z) > material.uniforms.uBox.value.x * 1.2 + (behind ? material.uniforms.uBox.value.y : 0);
        material.side = behind && far ? THREE.FrontSide : THREE.BackSide;
      });
      mesh.renderOrder = 6; this.attached.add(mesh);
    }
    if (o.skin) {
      const material = tune(new THREE.ShaderMaterial({vertexShader: SKIN_VERT, fragmentShader: SKIN_FRAG, defines: {STEPS: this.q.layer, ...(o.shock ? {LAYER: 1} : {})}, uniforms: {...layer(), uWind: {value: V3(0, 0, 1)}, uToCraft: {value: new THREE.Matrix4()}}, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -2}), true);
      for (const mesh of solids(this.craft.object)) {
        const skin = watch(new THREE.Mesh(mesh.geometry, material), (renderer) => { if (this._wind) this._wind.draw(renderer); });
        skin.userData.keep = true; skin.name = "hot surface"; skin.renderOrder = 3; skin.visible = false; mesh.add(skin); this.parts.skins.push(skin);
      }
      this._skin = material;
    }
    const points = (count, head) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(count * 3), 3)); g.setAttribute("aLook", new THREE.BufferAttribute(new Float32Array(count * 4), 4));
      const material = tune(new THREE.ShaderMaterial({vertexShader: POINT_VERT, fragmentShader: POINT_FRAG, defines: head ? {HEAD: 1} : {}, uniforms: {uView: {value: new THREE.Vector4(head ? 3.4 : 1.1, 0.002, head ? 0.45 : 0, head ? 1 : 0)}}}), true);
      const p = watch(new THREE.Points(g, material)); p.renderOrder = 8; p.visible = false; this.attached.add(p); return p;
    };
    if (o.sparks) this.parts.sparks = points(this.q.sparks, false);
    if (o.head) this.parts.head = points(1, true);
    if (o.trail) {
      this.parts.train = new Tube(6 * this.q.per + 2, this.q.sides, {glow: true, soft: 1.6, lumps: 0.55, grain: 9, least: 1.2, keep: 0.3});
      this.object.add(this.parts.train.mesh);
    }
  }

  _buildContrails() {
    const o = this.contrails, a = this.anchors, {radii, center} = this.shape;
    let from = o.from;
    if (typeof from === "string") {
      if (!["nozzles", "wingTips", "tail"].includes(from)) throw fail(`contrails from: "${from}"${hint(from, ["nozzles", "wingTips", "tail"])}; one of: nozzles, wingTips, tail, or a list of places [[x, y, z], ...] in the craft's axes`);
      const list = from === "tail" ? [] : (a[from] ?? []).map((n) => n.p);
      from = list.length ? list : [a.tail ? a.tail.p : [center[0], center[1], center[2] - radii[2]]];
    }
    if (!Array.isArray(from) || !from.every((p) => Array.isArray(p) && p.length === 3)) throw fail("contrails from: nozzles, wingTips, tail, or a list of places [[x, y, z], ...] in the craft's axes");
    // engines side by side leave one trail: places nearer than 1.5 m across are joined, at most four trails
    const joined = [];
    for (const p of from) { const near = joined.find((j) => Math.abs(j.p[0] / j.n - p[0]) < 1.5); if (near) { near.p = near.p.map((v, i) => v + p[i]); near.n++; } else joined.push({p: p.slice(), n: 1}); }
    this._contrailFrom = joined.slice(0, 4).map((j) => j.p.map((v) => v / j.n));
    const kind = {...TRAILS.contrail, life: o.life}, levels = Math.ceil(Math.log2(kind.life / (kind.step * this.q.per) + 1)) + 1;
    this._contrail = kind;
    for (let i = 0; i < this._contrailFrom.length; i++) { const tube = new Tube(levels * this.q.per + 2, this.q.sides, {sky: this.sky, soft: 1.3, lumps: kind.lumps, grain: 1.7, least: 0.6, keep: 0.25}); this.parts.contrails.push(tube); this.object.add(tube.mesh); this._vapours.push(tube.mesh); }
  }

  _buildVapour() {
    const o = this.vapour, a = this.anchors, {radii, center} = this.shape;
    const mist = (name) => {
      const material = tune(new THREE.ShaderMaterial({vertexShader: MIST_VERT, fragmentShader: MIST_FRAG, uniforms: {uBack: {value: new THREE.Matrix3()}, uSunDir: {value: V3(0, 1, 0)}, uSun: {value: V3(1, 1, 1)}, uSky: {value: V3(0.2, 0.25, 0.3)}, uMist: {value: new THREE.Vector2(0, 0)}}}), false);
      const mesh = new THREE.Mesh(this._ball ?? (this._ball = new THREE.IcosahedronGeometry(1, 3)), material), back = new THREE.Matrix4(), eye = V3();
      watch(mesh, (renderer, camera) => {
        material.uniforms.uBack.value.setFromMatrix4(back.copy(mesh.matrixWorld).invert());
        material.side = mesh.worldToLocal(eye.setFromMatrixPosition(camera.matrixWorld)).length() < 1.05 ? THREE.BackSide : THREE.FrontSide;
      });
      mesh.renderOrder = 4; mesh.visible = false; mesh.name = name; this.attached.add(mesh); this._vapours.push(mesh);
      return mesh;
    };
    // the cone: a dense thin disc of mist across the flow and a longer, thinner one behind it
    if (o.cone) this.parts.cone = [mist("vapour cone"), mist("vapour cone")];
    const tips = (a.wingTips ?? []).map((w) => w.p);
    if (o.tips && tips.length) {
      const kind = TRAILS.tip, levels = Math.ceil(Math.log2(kind.life / (kind.step * this.q.per) + 1)) + 1;
      this._tipFrom = tips;
      for (let i = 0; i < tips.length; i++) { const tube = new Tube(levels * this.q.per + 2, this.q.sides, {sky: null, soft: 1.2, lumps: kind.lumps, grain: 14}); this.parts.tips.push(tube); this.object.add(tube.mesh); this._vapours.push(tube.mesh); }
    }
    if (o.wings && tips.length) {
      // a sheet over each wing half: two flat patches of mist just above the upper surface
      const chord = 0.3 * radii[2];
      for (const tip of tips) for (const share of [0.4, 0.74]) {
        const mesh = mist("wing vapour"), k = 1 - 0.45 * share;
        mesh.position.set(tip[0] * share, tip[1] + 0.22 + 0.02 * Math.abs(tip[0]) * (1 - share), mix(center[2], tip[2], share) + chord * 0.1 * k);
        mesh.scale.set(Math.abs(tip[0]) * 0.36, 0.2, chord * 1.15 * k).multiplyScalar(2.6);
        mesh.rotation.z = Math.atan2(tip[1] - center[1], Math.abs(tip[0])) * Math.sign(tip[0]) * 0.5;
        this.parts.mists.push(mesh);
      }
    }
  }

  _buildExhaust() {
    const o = this.exhaust, craft = this.craft, tube = new THREE.CylinderGeometry(1, 1, 1, 20, 1, false); tube.translate(0, -0.5, 0);
    const make = (exit) => {
      const material = tune(new THREE.ShaderMaterial({vertexShader: EXHAUST_VERT, fragmentShader: EXHAUST_FRAG, defines: {REACH: EXHAUST_REACH.toFixed(1)}, side: THREE.BackSide,
        uniforms: {uCore: {value: V3()}, uEdge: {value: V3()}, uShape: {value: new THREE.Vector4(exit, 0.05, 12, exit * 3)}, uNow: {value: new THREE.Vector4()}, uMore: {value: new THREE.Vector4(2, 0.4, 1, 0.2)}}}), true);
      const mesh = watch(new THREE.Mesh(tube, material)); mesh.renderOrder = 5; mesh.visible = false; mesh.name = "exhaust in air"; mesh.userData.keep = true;
      return mesh;
    };
    if (o.nozzles) {
      if (!Array.isArray(o.nozzles) || !o.nozzles.every((n) => n && Array.isArray(n.p) && n.radius > 0)) throw fail("exhaust nozzles: a list of {p: [x, y, z], n: [x, y, z] (the way the gas leaves; default the tail's), radius} in the craft's axes");
      for (const n of o.nozzles) { const mesh = make(n.radius); mesh.position.set(...n.p); mesh.quaternion.setFromUnitVectors(V3(0, -1, 0), V3(...(n.n ?? [0, 0, -1])).normalize()); this.attached.add(mesh); this.parts.exhausts.push({mesh, exit: n.radius, engine: null}); }
    } else if (craft.engines && craft.engines.length) {
      // the craft kit's engines: one exhaust where each of its plumes is, which it replaces
      for (const e of craft.engines) if (e.plume) { const mesh = make(e.exit); mesh.position.copy(e.plume.position); mesh.quaternion.copy(e.plume.quaternion); e.plume.parent.add(mesh); this.parts.exhausts.push({mesh, exit: e.exit, engine: e}); }
    } else throw fail("exhaust: the craft has no engines of the craft kit: give exhaust: {nozzles: [{p: [x, y, z], n: [0, 0, -1], radius}]}");
  }

  // the flight's numbers at scene time t, each replaced by what update() was given
  _state(t, given) {
    const now = this.track ? this.track.now(t) : null, object = this.craft.object, pick = (key, fallback) => (given[key] !== undefined ? value(given[key], t) : now ? now[key] : fallback);
    object.updateMatrixWorld(true);
    const position = now ? now.position : vec(object.getWorldPosition(V3())), quaternion = now ? now.quaternion : object.getWorldQuaternion(new THREE.Quaternion()).toArray();
    let velocity = vec(value(given.velocity, t)) ?? (now ? now.velocity : null);
    if (!velocity) { const nose = V3(0, 0, 1).applyQuaternion(new THREE.Quaternion(...quaternion)); velocity = [nose.x, nose.y, nose.z]; }
    const height = pick("height", position[1]), air = given.air !== undefined ? value(given.air, t) : airDensity(height, this.options.scaleHeight);
    const full = this.reentry ? this.reentry.full : 1, heatGiven = given.heating !== undefined;
    return {t, time: now ? now.time : t, position, quaternion, velocity, speed: Math.hypot(...velocity), heating: now ? now.heating : 0, heat: clamp(heatGiven ? value(given.heating, t) : now ? now.heating / full : 0), heatGiven, mach: pick("mach", 0), load: pick("load", 1), height, aboveGround: pick("aboveGround", height), air,
      throttle: given.throttle !== undefined ? value(given.throttle, t) : null, boost: clamp(value(given.boost, t) ?? 0), pulse: value(given.pulse, t) ?? 1};
  }

  // the craft at flight second tau: from the flight, from `path`, or straight back along the velocity now
  _past(tau, s) {
    if (this.track) return this.track.at(tau);
    const d = tau - s.time, own = this.options.path ? this.options.path(tau) : null;
    if (own) return {heating: s.heating, mach: s.mach, load: s.load, height: s.height, quaternion: s.quaternion, velocity: s.velocity, ...own, time: tau};
    return {...s, time: tau, position: s.position.map((p, i) => p + s.velocity[i] * d)};
  }

  // a trail from a place of the craft: rings at fixed birth times, each where that place was then
  _lay(tube, kind, from, s, size, look) {
    const times = trailTimes(s.time, {life: kind.life, step: kind.step, per: this.q.per}), q = new THREE.Quaternion(), p = V3(), points = [];
    for (const tau of times) {
      const then = this._past(tau, s), age = s.time - tau;
      p.set(...from).applyQuaternion(q.set(...then.quaternion));
      const radius = trailRadius(age, kind, size), sway = kind.wave * radius * smooth(0.15, 0.8, age / kind.life);
      const made = look(then, age);
      points.push({p: [then.position[0] + p.x + sway * Math.sin(tau * 0.9 + from[0]), then.position[1] + p.y + sway * 0.6 * Math.sin(tau * 1.37 + 2 + from[0]), then.position[2] + p.z + sway * Math.cos(tau * 1.1 + from[0])],
        tangent: then.velocity, radius, alpha: trailAlpha(age, kind) * made.alpha, along: tau, color: made.color});
    }
    tube.lay(points, s.position);
  }

  /** The effects at scene time `t` (after the craft's own update). Without options everything comes from the
   * flight; each number can be given instead (a number or a function of t): `velocity` ([x, y, z] in the
   * scene's axes, metres a second: the windward side), `heating` (0..1 as shown, after `reentry.full`),
   * `mach`, `load` (g), `height` (metres), `air` (density over sea level's), `throttle` (0..1, a list per
   * engine; default what the craft's own engines do), `boost` (the afterburner, 0..1), `pulse` (multiplies the
   * glow and the exhaust: a level of ctx.music), `sun` (a new direction). Returns the effects. */
  update(t = 0, given = {}) {
    known("update options", given, UPDATE_KEYS);
    const s = this._state(t, given), object = this.craft.object, sky = this.sky;
    const turn = new THREE.Quaternion(...s.quaternion), wind = V3(...s.velocity).normalize(), local = wind.clone().applyQuaternion(turn.clone().invert());
    // the light vapour is seen by: the air's own at the craft's height, or what was given
    const sunDir = vec(given.sun ?? this.options.sun) ?? (sky ? vec(sky.sun) : [0.3, 0.8, 0.5]);
    let sun = this.options.light, ambient = this.options.ambient, expose = 1;
    if (sky && sky.state && sky.model) {
      const up = sky.state.up, mus = clamp(up[0] * sunDir[0] + up[1] * sunDir[1] + up[2] * sunDir[2], -1, 1), k = sky.options.light * sky.state.gain;
      sun = sunlightAt(sky.model, Math.max(s.height, 0), mus, sky.options.sunSize).map((x, i) => x * sky.options.color[i] * k);
      ambient = skyAmbient(sky.model, Math.max(s.height, 0), mus, {steps: 8}).map((x, i) => x * sky.options.color[i] * k);
      expose = sky.options.exposure === "film" ? Math.min(sky.state.gain, 1) : sky.state.gain;
    }
    for (const mesh of this._vapours) { const u = mesh.material.uniforms; u.uSunDir.value.set(...sunDir).normalize(); u.uSun.value.set(...sun); u.uSky.value.set(...ambient); }
    Object.assign(this.state, s, {wind: [local.x, local.y, local.z], sunlight: sun, ambient, expose});
    if (this.reentry) this._reentry(s, wind, local, expose);
    if (this.contrails) this._contrails(s);
    if (this.vapour) this._vapour(s, local);
    if (this.exhaust) this._exhaust(s, expose);
    object.updateMatrixWorld(true);
    return this;
  }

  _reentry(s, wind, local, expose) {
    const o = this.reentry, parts = this.parts, {center, radii} = this.shape, big = Math.max(...radii);
    const heat = clamp(s.heat * s.pulse), on = heat > 0.02, glow = o.level * expose, flick = flicker(s.t, 3);
    this.state.heat = heat;
    const x = V3(1, 0, 0), y = V3();
    if (Math.abs(local.x) > 0.95) x.set(0, 1, 0);
    x.addScaledVector(local, -x.dot(local)).normalize(); y.copy(local).cross(x);
    if (this._wind) this._wind.aim(x, y, local);
    for (const material of [parts.shock ? parts.shock.material : null, this._skin]) if (material) {
      const u = material.uniforms, half = this._wind ? this._wind.half : 1;
      u.uMap.value = this._wind ? this._wind.target.texture : null; u.uFrame.value.set(x.x, y.x, local.x, x.y, y.y, local.y, x.z, y.z, local.z);
      u.uLayer.value.set(half, o.thickness * big, half * 0.98, half * 1.9); if (u.uRadii) u.uWind.value.copy(local); u.uNow.value.set(heat, s.t, 0, 0); u.uLevel.value = glow * (material === this._skin ? 1 : flick);
    }
    if (parts.shock) parts.shock.visible = on;
    if (parts.wake) {
      const u = parts.wake.material.uniforms;
      u.uFrame.value.set(x.x, y.x, local.x, x.y, y.y, local.y, x.z, y.z, local.z);
      // the stream is as wide as the craft is across the flow: the ellipsoid's reach along each of the frame's axes
      const reach = (d) => Math.hypot(d.x * radii[0], d.y * radii[1], d.z * radii[2]);
      u.uWake.value.set(reach(x) * 0.85, reach(y) * 0.85, big * 2 * o.length, big * 2); u.uNow.value.set(heat, s.t, 0, 0); u.uBox.value.x = Math.max(reach(x), reach(y)) * 0.85 * 0.9 * 2.05 * 1.9;
      parts.wake.visible = on; u.uLevel.value = glow * flick;
    }
    if (this._skin) { this._skin.uniforms.uWind.value.copy(wind); this._skin.uniforms.uToCraft.value.copy(this.craft.object.matrixWorld).invert(); for (const skin of parts.skins) skin.visible = on; }
    if (parts.sparks) {
      const P = parts.sparks.geometry.attributes.position, L = parts.sparks.geometry.attributes.aLook, count = P.count, lit = Math.round(count * smooth(0.25, 0.9, heat)), side = V3(), d = V3(), toWind = new THREE.Quaternion().setFromUnitVectors(V3(0, 0, 1), local);
      for (let i = 0; i < count; i++) {
        const k = sparkAt(i, s.t, this.seed);
        // born on the windward rim of the ellipsoid, carried back with the flow, drifting off it
        side.set(Math.cos(TAU * k.a), Math.sin(TAU * k.a), 0).applyQuaternion(toWind);
        d.copy(side).multiplyScalar(0.85).addScaledVector(local, 0.1 + 0.5 * k.b).normalize();
        const back = big * (0.4 + 5.5 * k.age * (0.6 + 0.8 * k.c)), out = 1 + 0.25 * k.age * k.b;
        P.setXYZ(i, center[0] + d.x * radii[0] * out - local.x * back, center[1] + d.y * radii[1] * out - local.y * back, center[2] + d.z * radii[2] * out - local.z * back);
        L.setXYZW(i, big * (0.004 + 0.005 * k.c), i < lit ? 2.2 * glow * (1 - k.age) * (1 - k.age) * smooth(0, 0.08, k.age) : 0, 0.45 + 0.5 * heat * (1 - k.age), 0);
      }
      P.needsUpdate = true; L.needsUpdate = true; parts.sparks.visible = lit > 0;
    }
    if (parts.head) {
      parts.head.geometry.attributes.position.setXYZ(0, center[0] + local.x * radii[0] * 0.2, center[1] + local.y * radii[1] * 0.2, center[2] + local.z * radii[2] * 0.6); parts.head.geometry.attributes.position.needsUpdate = true;
      parts.head.geometry.attributes.aLook.setXYZW(0, big * 0.5, heatLevel(heat) * 1.4, heat, 0); parts.head.geometry.attributes.aLook.needsUpdate = true;
      parts.head.visible = on; parts.head.material.uniforms.uLevel.value = glow * flick;
    }
    if (parts.train) {
      const kind = {...TRAILS.plasma, life: o.persist}, full = o.full, tracked = !!this.track;
      this._lay(parts.train, kind, [center[0], center[1], center[2] - radii[2] * 0.6], s, big * 0.75, (then, age) => {
        const born = tracked && !s.heatGiven ? clamp(then.heating / full) : heat, cooled = born * (1 - 0.75 * smooth(0, kind.life, age));
        const l = heatLight(cooled * s.pulse).map((c) => c * 0.55 * glow);
        return {alpha: smooth(0.03, 0.2, born), color: l};
      });
      parts.train.mesh.visible = parts.train.mesh.visible && (on || tracked);
    }
  }

  _contrails(s) {
    const o = this.contrails, kind = this._contrail;
    this.parts.contrails.forEach((tube, i) => this._lay(tube, kind, this._contrailFrom[i], s, o.size * Math.max(1, 0.09 * Math.max(...this.shape.radii)), (then) => ({alpha: kind.density * o.level * (o.always ? 1 : contrailLevel(then.height, o.band)), color: o.color})));
  }

  _vapour(s, local) {
    const o = this.vapour, parts = this.parts, {center, radii} = this.shape;
    const cone = o.cone ? coneLevel(s.mach, s.air) * o.level : 0, wings = wingVapour(s.load, s.air) * o.level;
    Object.assign(this.state, {cone, wingVapour: wings});
    if (parts.cone) {
      const body = Math.min(radii[0], radii[1] * 1.6, radii[2]), aim = new THREE.Quaternion().setFromUnitVectors(V3(0, 0, 1), local);
      parts.cone.forEach((mesh, i) => {
        const along = radii[2] * (i ? -0.34 : -0.14), wide = body * (i ? 2.5 : 2.0), deep = radii[2] * (i ? 0.22 : 0.05);
        mesh.position.set(center[0] + local.x * along, center[1] + local.y * along, center[2] + local.z * along); mesh.quaternion.copy(aim); mesh.scale.set(wide, wide, deep).multiplyScalar(2.6);
        mesh.visible = cone > 0.01; mesh.material.uniforms.uMist.value.set((i ? 0.5 : 1.6) * cone / Math.max(deep, 0.2) * 1.2, 11 * i + 0.6 * s.t);
      });
    }
    parts.tips.forEach((tube, i) => this._lay(tube, TRAILS.tip, this._tipFrom[i], s, 1, (then) => ({alpha: TRAILS.tip.density * o.level * wingVapour(then.load, airDensity(then.height, this.options.scaleHeight)), color: [1, 1, 1]})));
    for (const mesh of parts.mists) { mesh.visible = wings > 0.01; mesh.material.uniforms.uMist.value.set(7 * wings * (0.9 + 0.1 * Math.sin(TAU * 4.1 * s.t + mesh.position.x)), mesh.position.x + 0.8 * s.t); }
  }

  _exhaust(s, expose) {
    const o = this.exhaust, air = o.air ?? s.air, shape = plumeShape(air, s.boost);
    this.state.plume = shape;
    this.parts.exhausts.forEach((e, i) => {
      let power = Array.isArray(s.throttle) ? (s.throttle[i] ?? 0) : s.throttle;
      const own = power === null && e.engine;                          // the craft's own engine: its plume's power now (it flickers already)
      if (own) power = e.engine.plume.visible ? e.engine.plume.material.uniforms.uNow.value.x : 0;
      power = clamp(power ?? 0, 0, 1.2) * (1 + 0.2 * s.boost) * s.pulse;
      if (e.engine) e.engine.plume.visible = false;
      const u = e.mesh.material.uniforms, f = power * (own ? 1 : flicker(s.t, i + 5));
      e.mesh.visible = power > 0.002;
      u.uShape.value.set(e.exit, shape.spread, shape.length, e.exit * (1 + shape.spread * shape.length * EXHAUST_REACH) * 1.9);
      u.uCore.value.set(...shape.core).multiplyScalar(shape.gain * o.level * expose); u.uEdge.value.set(...shape.edge).multiplyScalar(shape.gain * o.level * expose);
      u.uNow.value.set(f, s.t, shape.diamonds * smooth(0.45, 0.9, power), shape.coreLength); u.uMore.value.set(shape.spacing, shape.coreRadius, shape.taper, shape.outer);
      if (e.engine && e.engine.glow) e.engine.glow.color.setRGB(0.02 + shape.edge[0] * f * 3.2, 0.02 + shape.edge[1] * f * 3.2, 0.02 + shape.edge[2] * f * 3.2);
    });
  }

  /** Take everything out of the scene and the craft and free it. */
  dispose() {
    const gone = [this.object, this.attached, ...this.parts.skins, ...this.parts.exhausts.map((e) => e.mesh)];
    if (this._wind) this._wind.dispose();
    for (const o of gone) { if (o.parent) o.parent.remove(o); o.traverse((m) => { if (m.material) m.material.dispose(); if (m.geometry && !m.userData.keep) m.geometry.dispose(); }); }
  }
}

/** The effects of a craft: `effects(craft, options)` → Effects. `craft`: a Craft or Plane (or anything with an
 * `object`, or an Object3D). Options: `flight` (ctx.flight) and `name` (the flight's; default the first):
 * every number then comes from the flight; `sky` (the air of vidgen/space-air: the light on vapour, the haze on
 * trails, the exposure, the scale height); `seed`; `quality` (fast | standard | fine); `shape` ({center, radii}:
 * the bounding ellipsoid in the craft's axes; default from the craft); `anchors` (named places, as a plane's);
 * `scaleHeight` (metres; default the sky's); `path` (a function of time → {position, quaternion, velocity} for
 * trails of a craft that is not on a flight); `sun`, `light`, `ambient` (the light on vapour without a sky);
 * and the four groups, each `true` or its own options:
 * `reentry` {full (the flight's heating shown as 1; default 0.65), level, shock, skin, wake, sparks, trail, head, thickness, length, persist},
 * `contrails` {from (nozzles | wingTips | tail | places), band ([from, full] metres), always, life, size, level, color},
 * `exhaust` {nozzles ([{p, n, radius}]; default the craft's engines), level, air},
 * `vapour` {cone, wings, tips, level}. */
export const effects = (craft, options = {}) => new Effects(craft, options);
