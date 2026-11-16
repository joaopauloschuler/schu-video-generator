// Parallel Space (v7): one three.js module for every scene of the music video (data.mode picks the set).
//
// Everything is a function of the song time T = data.t0 + t on a grid of 52 frames per bar
// (138.46 BPM at 30 fps): no state is carried from frame to frame or from scene to scene, and
// every "random" number comes from a seeded generator, so a scene renders the same every time,
// in any order. The pictures follow the music through ps_audio.json (scripts/make_ps_audio.py):
// spectrum bands, level and onsets measured from the track, and the score's own notes (kick,
// big drums, booms, ticks, every note of the hook with its pitch).
//
// The look: light on black. Lines are drawn as soft glowing strokes (a quad per segment, a bright
// core with a halo), faces as faint glass with bright rims, the sky is a nebula baked once into a
// cube map and lit from inside, and the frame goes through bloom, a filmic tone curve, a colour
// grade per section, a slight chromatic fringe, a vignette and fine grain.
//
// Rules kept from the owner's notes on earlier versions: the kick pulses the BRIGHTNESS of
// objects, never the zoom; rotations are smooth (no beat flicks); nothing large sweeps through
// the camera as stripes (segments are cut at the near plane and wrapped objects fade in far away).
import * as THREE from "three";
import {EffectComposer} from "three/addons/postprocessing/EffectComposer.js";
import {RenderPass} from "three/addons/postprocessing/RenderPass.js";
import {UnrealBloomPass} from "three/addons/postprocessing/UnrealBloomPass.js";
import {ShaderPass} from "three/addons/postprocessing/ShaderPass.js";

const BAR = 52 / 30, BEAT = BAR / 4, S16 = BAR / 16, TAU = Math.PI * 2;
let R, S, C, composer, bloom, fin, W, H, AU, mode, t0;
let titleEl, endEl;
const O = {};
const uRes = {value: new THREE.Vector2(1280, 720)}, uK = {value: 1};

// ---------- small helpers ----------
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const mix = (a, b, u) => a + (b - a) * u;
const sstep = (a, b, x) => { const u = clamp((x - a) / (b - a)); return u * u * (3 - 2 * u); };
const ease = (u) => { u = clamp(u); return u * u * u * (u * (u * 6 - 15) + 10); };
function rng(seed) { let s = seed >>> 0; return () => { s = (s + 0x6D2B79F5) >>> 0; let r = Math.imul(s ^ (s >>> 15), 1 | s); r ^= r + Math.imul(r ^ (r >>> 7), 61 | r); return ((r ^ (r >>> 14)) >>> 0) / 4294967296; }; }
const hash1 = (i, k = 0) => { const x = Math.sin(i * 127.1 + k * 311.7 + 0.5) * 43758.5453; return x - Math.floor(x); };
const hx = (hex, m = 1) => new THREE.Color(hex).multiplyScalar(m);
const TMP = new THREE.Color();
const lerpC = (a, b, u, m = 1) => TMP.copy(a).lerp(b, clamp(u)).multiplyScalar(m);

// colours (sRGB hex; three.js converts them to linear light)
const ICE = hx(0x9fdcff), CYAN = hx(0x35e8ff), TEAL = hx(0x1fd0c0), BLUE = hx(0x3f6bff), INDIGO = hx(0x5a48ff), VIO = hx(0x9b5cff),
  MAG = hx(0xff3fb4), ROSE = hx(0xff7aa8), AMBER = hx(0xffa63c), GOLD = hx(0xffd166), ORANGE = hx(0xff6a2a), EMBER = hx(0xff3a24),
  WHITE = hx(0xfff4e6), GREEN = hx(0x5dffb0);

// ---------- the music as data ----------
function loadAudio(j) {
  const val = {}; [...j.alphabet].forEach((ch, i) => { val[ch] = i / 63; });
  const dec = (s) => { const a = new Float32Array(s.length); for (let i = 0; i < s.length; i++) a[i] = val[s[i]]; return a; };
  const s16 = j.bar_seconds / 16;
  const hits = {}, notes = {};
  for (const k in j.hits) hits[k] = {t: Float32Array.from(j.hits[k], (e) => e[0] * s16), g: Float32Array.from(j.hits[k], (e) => e[1])};
  for (const k in j.notes) notes[k] = {t: Float32Array.from(j.notes[k], (e) => e[0] * s16), d: Float32Array.from(j.notes[k], (e) => e[1] * s16), p: Float32Array.from(j.notes[k], (e) => e[2])};
  return {n: j.n, nb: j.nbands, bands: dec(j.bands), level: dec(j.level), low: dec(j.low), flux: dec(j.flux), hits, notes};
}
function ser(a, T) { const x = clamp(T * 30, 0, AU.n - 1.001), i = Math.floor(x), f = x - i; return a[i] * (1 - f) + a[i + 1] * f; }
const level = (T) => ser(AU.level, T), lowE = (T) => ser(AU.low, T), flux = (T) => ser(AU.flux, T);
function band(T, b) { const x = clamp(T * 30, 0, AU.n - 1.001), i = Math.floor(x), f = x - i; return AU.bands[i * AU.nb + b] * (1 - f) + AU.bands[(i + 1) * AU.nb + b] * f; }
function lastIdx(ts, T) { let lo = 0, hi = ts.length - 1, k = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (ts[m] <= T + 1e-5) { k = m; lo = m + 1; } else hi = m - 1; } return k; }
// the envelope of a drum: 1 (1.5 on an accent) at each hit, falling with `decay` seconds
function env(name, T, decay) {
  const h = AU.hits[name]; if (!h) return 0;
  let v = 0;
  for (let j = lastIdx(h.t, T), n = 0; j >= 0 && n < 3; j--, n++) v = Math.max(v, Math.min(h.g[j], 1.25) * Math.exp(-(T - h.t[j]) / decay));
  return v;
}
const kick = (T) => env("kick", T, 0.1);
// the note a track is playing (or played last): index, pitch, seconds since it began, its length
function note(name, T) { const n = AU.notes[name], i = n ? lastIdx(n.t, T) : -1; return i < 0 ? null : {i, p: n.p[i], age: T - n.t[i], d: n.d[i]}; }
// how loud a held note sounds now: a quick attack, held, then a release
function noteAmp(name, T, attack = 0.05, release = 0.5) { const q = note(name, T); if (!q) return 0; return q.age < q.d ? clamp(q.age / attack) : Math.exp(-(q.age - q.d) / release); }

// ---------- glowing lines: a quad per segment, a bright core and a soft halo, added to the frame ----------
const QUAD = new THREE.BufferGeometry();
QUAD.setAttribute("position", new THREE.Float32BufferAttribute([-1, 0, 0, 1, 0, 0, -1, 1, 0, 1, 1, 0], 3));
QUAD.setIndex([0, 1, 2, 2, 1, 3]);
const GLOW_VERT = /* glsl */`
attribute vec3 iA; attribute vec3 iB; attribute vec4 iC;
uniform vec2 uRes; uniform float uK, uPx, uWorld, uHalo, uMax; uniform vec2 uFog; uniform vec3 uTint;
varying vec3 vC; varying vec3 vP; varying float vW;
void main(){
  vec4 a = modelViewMatrix * vec4(iA, 1.0), b = modelViewMatrix * vec4(iB, 1.0);
  float nz = -0.35;
  bool ba = a.z > nz, bb = b.z > nz;
  if (ba && bb) { gl_Position = vec4(0.0, 0.0, 2.0, 1.0); vC = vec3(0.0); vP = vec3(0.0); vW = 1.0; return; }
  if (ba) a = mix(b, a, (nz - b.z) / (a.z - b.z));
  if (bb) b = mix(a, b, (nz - a.z) / (b.z - a.z));
  vec4 ca = projectionMatrix * a, cb = projectionMatrix * b;
  vec2 sa = ca.xy / ca.w * uRes * 0.5, sb = cb.xy / cb.w * uRes * 0.5;
  vec2 dir = sb - sa; float len = length(dir); dir = len > 1e-4 ? dir / len : vec2(1.0, 0.0);
  vec2 nrm = vec2(-dir.y, dir.x);
  float e = position.y;
  vec4 c = mix(ca, cb, e); float vz = mix(a.z, b.z, e);
  float ww = uWorld * iC.a * projectionMatrix[1][1] * uRes.y * 0.5 / max(-vz, 0.001);
  float minw = uPx * iC.a * uK;
  float thin = clamp(ww / minw, 0.3, 1.0);
  float w = uWorld > 0.0 ? max(ww, minw) : minw;
  if (uWorld <= 0.0) thin = 1.0;
  w = min(w, uMax * uK);
  float hw = w * (0.5 + uHalo) + 1.0;
  vec2 pos = mix(sa, sb, e) + nrm * position.x * hw + dir * (e * 2.0 - 1.0) * hw;
  gl_Position = vec4(pos / (uRes * 0.5) * c.w, c.z, c.w);
  vP = vec3(e * len + (e * 2.0 - 1.0) * hw, position.x * hw, len); vW = w;
  float fog = 1.0 - smoothstep(uFog.x, uFog.y, -vz);
  vC = iC.rgb * uTint * fog * thin;
}`;
const GLOW_FRAG = /* glsl */`
uniform float uHalo, uHaloGain;
varying vec3 vC; varying vec3 vP; varying float vW;
void main(){
  float along = clamp(vP.x, 0.0, vP.z);
  float d = length(vec2(vP.x - along, vP.y));
  if (!(d >= 0.0 && d < 1e20)) { gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0); return; }
  float core = 1.0 - smoothstep(vW * 0.5 - 0.7, vW * 0.5 + 0.7, d);
  float s = max(vW * uHalo * 0.45, 0.6);
  float halo = exp(-d * d / (2.0 * s * s));
  gl_FragColor = vec4(vC * (core + uHaloGain * halo), 1.0);
}`;
class Glow {
  constructor(max, o = {}) {
    this.max = max; this.a = new Float32Array(max * 3); this.b = new Float32Array(max * 3); this.c = new Float32Array(max * 4).fill(1);
    const g = new THREE.InstancedBufferGeometry();
    g.index = QUAD.index; g.setAttribute("position", QUAD.attributes.position);
    g.setAttribute("iA", this.ia = new THREE.InstancedBufferAttribute(this.a, 3));
    g.setAttribute("iB", this.ib = new THREE.InstancedBufferAttribute(this.b, 3));
    g.setAttribute("iC", this.ic = new THREE.InstancedBufferAttribute(this.c, 4));
    g.instanceCount = max; this.geo = g;
    this.mat = new THREE.ShaderMaterial({
      uniforms: {uRes, uK, uMax: {value: o.max ?? 7}, uPx: {value: o.px ?? 1.5}, uWorld: {value: o.world ?? 0}, uHalo: {value: o.halo ?? 1.4}, uHaloGain: {value: o.haloGain ?? 0.3},
        uTint: {value: new THREE.Color(1, 1, 1)}, uFog: {value: new THREE.Vector2(o.fog ? o.fog[0] : 1e5, o.fog ? o.fog[1] : 1e6)}},
      vertexShader: GLOW_VERT, fragmentShader: GLOW_FRAG, side: THREE.DoubleSide, transparent: true, depthWrite: false, depthTest: o.depthTest ?? true, blending: THREE.AdditiveBlending,
    });
    if (o.inPortal) portalOnly(this.mat);
    this.mesh = new THREE.Mesh(g, this.mat); this.mesh.frustumCulled = false; this.mesh.renderOrder = o.order ?? 5;
    (o.parent ?? S).add(this.mesh);
  }
  seg(i, ax, ay, az, bx, by, bz) { const k = i * 3; this.a[k] = ax; this.a[k + 1] = ay; this.a[k + 2] = az; this.b[k] = bx; this.b[k + 1] = by; this.b[k + 2] = bz; }
  dot(i, x, y, z) { this.seg(i, x, y, z, x, y, z); }
  col(i, c, m = 1, w = 1) { const k = i * 4; this.c[k] = c.r * m; this.c[k + 1] = c.g * m; this.c[k + 2] = c.b * m; this.c[k + 3] = w; }
  rgb(i, r, g, b, w = 1) { const k = i * 4; this.c[k] = r; this.c[k + 1] = g; this.c[k + 2] = b; this.c[k + 3] = w; }
  hide(i) { const k = i * 4; this.c[k] = this.c[k + 1] = this.c[k + 2] = 0; }
  tint(c, m = 1) { this.mat.uniforms.uTint.value.copy(c).multiplyScalar(m); return this; }
  count(n) { this.geo.instanceCount = Math.min(n, this.max); }
  flush(pos = true, col = true) { if (pos) { this.ia.needsUpdate = true; this.ib.needsUpdate = true; } if (col) this.ic.needsUpdate = true; }
  // a fixed set of segments (pairs of points in one flat array), all one colour
  static from(arr, o = {}) {
    const n = arr.length / 6, g = new Glow(n, o);
    for (let i = 0; i < n; i++) g.seg(i, arr[i * 6], arr[i * 6 + 1], arr[i * 6 + 2], arr[i * 6 + 3], arr[i * 6 + 4], arr[i * 6 + 5]);
    return g;
  }
}
// drawn only where a portal's window has marked the frame (the other universe)
function portalOnly(mat) { mat.stencilWrite = true; mat.stencilFunc = THREE.EqualStencilFunc; mat.stencilRef = 1; mat.depthTest = false; return mat; }
const circlePts = (n, r, z = 0, rot = 0) => { const a = []; for (let i = 0; i < n; i++) { const u = rot + (i / n) * TAU, v = rot + ((i + 1) / n) * TAU; a.push(Math.cos(u) * r, Math.sin(u) * r, z, Math.cos(v) * r, Math.sin(v) * r, z); } return a; };

// ---------- glass faces: almost nothing face-on, a bright rim at grazing angles ----------
const FACE_VERT = "varying vec3 vV; void main(){ vec4 mv = modelViewMatrix * vec4(position, 1.0); vV = mv.xyz; gl_Position = projectionMatrix * mv; }";
const FACE_FRAG = /* glsl */`
uniform vec3 uCol; uniform float uBase, uRim; varying vec3 vV;
void main(){
  vec3 n = normalize(cross(dFdx(vV), dFdy(vV))); vec3 v = normalize(-vV);
  float f = 1.0 - abs(dot(n, v));
  float facet = 0.35 + 0.65 * abs(dot(n, normalize(vec3(0.35, 0.8, 0.5))));
  gl_FragColor = vec4(uCol * (uBase * facet + uRim * f * f * f), 1.0);
}`;
function faceMat(c, base = 0.05, rim = 0.5, inPortal = false) {
  const m = new THREE.ShaderMaterial({uniforms: {uCol: {value: c.clone()}, uBase: {value: base}, uRim: {value: rim}}, vertexShader: FACE_VERT, fragmentShader: FACE_FRAG,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide});
  return inPortal ? portalOnly(m) : m;
}
const GEO = {}, EDGE = {};
function shapeLib() {
  const g = {ico: new THREE.IcosahedronGeometry(1, 0), octa: new THREE.OctahedronGeometry(1, 0), tetra: new THREE.TetrahedronGeometry(1.15, 0),
    dodeca: new THREE.DodecahedronGeometry(1, 0), cube: new THREE.BoxGeometry(1.2, 1.2, 1.2)};
  for (const k in g) { GEO[k] = g[k]; EDGE[k] = Array.from(new THREE.EdgesGeometry(g[k], 1).attributes.position.array); }
}
const KINDS = ["octa", "tetra", "ico", "dodeca", "cube"];
// a crystal: glass faces and glowing edges
function crystal(kind, lineC, faceC, o = {}) {
  const g = new THREE.Group();
  const faces = new THREE.Mesh(GEO[kind], faceMat(faceC, o.base ?? 0.05, o.rim ?? 0.55, o.inPortal)); faces.renderOrder = 4;
  const edges = Glow.from(EDGE[kind], {parent: g, px: o.px ?? 1.3, world: o.world ?? 0.035, halo: 1.2, haloGain: 0.3, fog: o.fog, inPortal: o.inPortal});
  edges.tint(lineC, o.gain ?? 1.6);
  g.add(faces); g.userData = {faces, edges, lineC: lineC.clone(), faceC: faceC.clone(), gain: o.gain ?? 1.6};
  (o.parent ?? S).add(g);
  return g;
}
// brighten a crystal (k: 0..1, the kick) without changing its size
function lightCrystal(g, k, dim = 1) {
  const u = g.userData;
  u.edges.mat.uniforms.uTint.value.copy(u.lineC).lerp(WHITE, 0.45 * k).multiplyScalar(u.gain * dim * (1 + 1.6 * k));
  u.faces.material.uniforms.uCol.value.copy(u.faceC).multiplyScalar(dim * (1 + 2.2 * k));
}

// ---------- the sky: a nebula baked into a cube map at load, lit from inside while it plays ----------
const SKY_VERT = "varying vec3 vD; void main(){ vD = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }";
const BAKE_FRAG = /* glsl */`
varying vec3 vD; uniform float uSeed;
float hash(vec3 p){ p = fract(p * 0.3183099 + vec3(0.1, 0.2, 0.3)); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float noise(vec3 p){
  vec3 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash(i), hash(i + vec3(1,0,0)), f.x), mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
             mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x), mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y), f.z);
}
float fbm(vec3 p){ float a = 0.5, s = 0.0; for (int i = 0; i < 6; i++) { s += a * noise(p); p = p * 2.02 + vec3(17.1, 9.4, 3.7); a *= 0.5; } return s; }
float stars(vec3 d, float scale, float cut){
  vec3 q = d * scale, c = floor(q);
  float h = hash(c + uSeed);
  vec3 o = vec3(hash(c + 3.1), hash(c + 7.7), hash(c + 13.3)) * 0.6 + 0.2;
  float r = length(q - c - o);
  float m = hash(c + 21.0); return step(cut, h) * smoothstep(0.16 + 0.14 * m * m, 0.0, r) * (0.15 + 0.85 * m * m * m);
}
void main(){
  vec3 d = normalize(vD), s = vec3(uSeed * 3.1, uSeed * 1.7, uSeed * 2.3);
  vec3 w = d + 0.55 * (vec3(fbm(d * 1.6 + s + 11.0), fbm(d * 1.6 + s + 23.0), fbm(d * 1.6 + s + 37.0)) - 0.5);
  float dens = fbm(w * 2.1 + s);
  float fil = 1.0 - abs(2.0 * fbm(w * 4.3 + s * 1.7 + 5.0) - 1.0); fil = fil * fil * fil;
  float dust = fbm(w * 3.1 + 50.0 - s);
  float st = stars(d, 90.0, 0.93) * 1.6 + stars(d, 170.0, 0.90) * 0.9 + stars(d, 300.0, 0.88) * 0.5;
  gl_FragColor = vec4(dens, fil, dust, st);
}`;
const SKY_FRAG = /* glsl */`
varying vec3 vD; uniform samplerCube uSky; uniform mat3 uM1, uM2; uniform vec3 uA, uB, uC, uL1, uL1c, uL2, uL2c;
uniform float uLo, uHi, uStar, uL1p, uL2p, uDust, uGain;
void main(){
  vec3 d = normalize(vD);
  vec4 s1 = textureCube(uSky, uM1 * d), s2 = textureCube(uSky, uM2 * d);
  float dens = smoothstep(uLo, uHi, s1.r * 0.62 + s2.r * 0.38);
  float fil = s1.g * (0.4 + s2.g);
  vec3 c = uA + uB * dens + uC * dens * dens * (0.25 + 1.5 * fil);
  c *= 1.0 - uDust * smoothstep(0.42, 0.7, s1.b) * 0.75;
  float body = 0.22 + 1.5 * dens * (0.5 + fil);
  c += uL1c * pow(max(dot(d, uL1), 0.0), uL1p) * body + uL2c * pow(max(dot(d, uL2), 0.0), uL2p) * body;
  c *= uGain;
  c += vec3(0.75, 0.86, 1.0) * s1.a * uStar * (1.0 - 0.75 * dens);
  gl_FragColor = vec4(c, 1.0);
}`;
function bakeSky(seed, size) {
  const rt = new THREE.WebGLCubeRenderTarget(size, {type: THREE.HalfFloatType, magFilter: THREE.LinearFilter, minFilter: THREE.LinearFilter, generateMipmaps: false});
  const cam = new THREE.CubeCamera(1, 100, rt), sc = new THREE.Scene();
  const m = new THREE.ShaderMaterial({uniforms: {uSeed: {value: seed}}, vertexShader: SKY_VERT, fragmentShader: BAKE_FRAG, side: THREE.BackSide, depthTest: false, depthWrite: false});
  sc.add(new THREE.Mesh(new THREE.BoxGeometry(20, 20, 20), m));
  cam.update(R, sc);
  m.dispose();
  return rt.texture;
}
function skyUniforms(tex) {
  return {uSky: {value: tex}, uM1: {value: new THREE.Matrix3()}, uM2: {value: new THREE.Matrix3()},
    uA: {value: hx(0x010308)}, uB: {value: hx(0x06203a)}, uC: {value: hx(0x2a7fa0)},
    uL1: {value: new THREE.Vector3(0, 0, -1)}, uL1c: {value: new THREE.Color(0, 0, 0)}, uL1p: {value: 6},
    uL2: {value: new THREE.Vector3(0, 1, 0)}, uL2c: {value: new THREE.Color(0, 0, 0)}, uL2p: {value: 6},
    uLo: {value: 0.32}, uHi: {value: 0.72}, uStar: {value: 1}, uDust: {value: 0.6}, uGain: {value: 1}};
}
const M4 = new THREE.Matrix4(), EUL = new THREE.Euler();
function skyTurn(u, T, k = 1) {
  u.uM1.value.setFromMatrix4(M4.makeRotationFromEuler(EUL.set(0.2 + T * 0.0031 * k, 0.6 + T * 0.0047 * k, 0.1)));
  u.uM2.value.setFromMatrix4(M4.makeRotationFromEuler(EUL.set(1.3 - T * 0.0043 * k, 2.1 + T * 0.0022 * k, 0.7 + T * 0.0035 * k)));
}
// the sky around the camera
function makeSky(seed) {
  const size = H >= 600 ? 640 : 256;
  const u = skyUniforms(bakeSky(seed, size));
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(2000, 2000, 2000), new THREE.ShaderMaterial({uniforms: u, vertexShader: SKY_VERT, fragmentShader: SKY_FRAG, side: THREE.BackSide, depthTest: false, depthWrite: false}));
  mesh.frustumCulled = false; mesh.renderOrder = -10; S.add(mesh);
  return {mesh, u};
}
function skyColors(sky, a, b, c, gain = 1) { sky.u.uA.value.copy(a); sky.u.uB.value.copy(b); sky.u.uC.value.copy(c); sky.u.uGain.value = gain; }
function skyLight(sky, n, dir, c, m, pow = 6) { const u = sky.u; (n === 1 ? u.uL1 : u.uL2).value.copy(dir).normalize(); (n === 1 ? u.uL1c : u.uL2c).value.copy(c).multiplyScalar(m); (n === 1 ? u.uL1p : u.uL2p).value = pow; }
const V3 = new THREE.Vector3(), V3b = new THREE.Vector3();

// ---------- a portal: a ring with a window onto the other universe (its own sky, its own things) ----------
const WIN_VERT = "varying vec3 vD; void main(){ vec4 w = modelMatrix * vec4(position, 1.0); vD = w.xyz - cameraPosition; gl_Position = projectionMatrix * viewMatrix * w; }";
function makePortal(radius, skyB, o = {}) {
  const g = new THREE.Group();
  const u = skyUniforms(skyB.u.uSky.value);
  for (const k in u) if (k !== "uGain") u[k] = skyB.u[k];
  u.uGain = {value: 1};
  const win = new THREE.Mesh(new THREE.CircleGeometry(radius, 72), new THREE.ShaderMaterial({uniforms: u, vertexShader: WIN_VERT, fragmentShader: SKY_FRAG, side: THREE.DoubleSide}));
  win.material.stencilWrite = true; win.material.stencilFunc = THREE.AlwaysStencilFunc; win.material.stencilRef = 1; win.material.stencilZPass = THREE.ReplaceStencilOp;
  win.renderOrder = -5; g.add(win);
  const ring = Glow.from(circlePts(96, radius), {parent: g, px: 2.2, world: radius * 0.035, halo: 1.6, haloGain: 0.4, fog: o.fog});
  const rim = Glow.from(circlePts(96, radius * 1.07), {parent: g, px: 1.0, world: radius * 0.008, halo: 1.2, haloGain: 0.3, fog: o.fog});
  const marks = [];
  for (let i = 0; i < 48; i++) { const a = (i / 48) * TAU, r0 = radius * 1.11, r1 = radius * (i % 4 === 0 ? 1.2 : 1.15); marks.push(Math.cos(a) * r0, Math.sin(a) * r0, 0, Math.cos(a) * r1, Math.sin(a) * r1, 0); }
  const dial = Glow.from(marks, {parent: g, px: 1.1, world: radius * 0.01, halo: 1.2, haloGain: 0.3, fog: o.fog});
  g.userData = {win, ring, rim, dial, radius, u};
  (o.parent ?? S).add(g);
  return g;
}
function lightPortal(p, ringC, m, rimC = WHITE, rm = 0.6, winGain = 1) { const u = p.userData; u.ring.tint(ringC, m); u.rim.tint(rimC, rm); u.u.uGain.value = winGain; }
// light the dial's marks one after the other, a clock: `step` is the mark of now, `e` how bright it is
function lightDial(p, c, base, step, e, n = 48) {
  const d = p.userData.dial;
  for (let i = 0; i < n; i++) { const back = ((step - i) % n + n) % n; d.col(i, c, base + (back < 6 ? e * Math.pow(0.55, back) * 3 : 0)); }
  d.flush(false, true);
}

// ---------- the tesseract: 16 corners, 32 edges, turned in 4D and projected ----------
const TES_V = [], TES_E = [];
for (let i = 0; i < 16; i++) TES_V.push([(i & 1) ? 1 : -1, (i & 2) ? 1 : -1, (i & 4) ? 1 : -1, (i & 8) ? 1 : -1]);
for (let i = 0; i < 16; i++) for (let j = i + 1; j < 16; j++) { let d = 0; for (let k = 0; k < 4; k++) if (TES_V[i][k] !== TES_V[j][k]) d++; if (d === 1) TES_E.push([i, j]); }
const PLANES = [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]];
function project4(v, angs, dist = 3.1, out = [0, 0, 0]) {
  let p0 = v[0], p1 = v[1], p2 = v[2], p3 = v[3];
  const p = [p0, p1, p2, p3];
  for (let i = 0; i < 6; i++) { const a = angs[i]; if (!a) continue; const c = Math.cos(a), s = Math.sin(a), i0 = PLANES[i][0], i1 = PLANES[i][1], u = p[i0], w = p[i1]; p[i0] = u * c - w * s; p[i1] = u * s + w * c; }
  const den = dist - p[3], sc = dist / (Math.abs(den) < 1e-3 ? 1e-3 : den);
  out[0] = p[0] * sc; out[1] = p[1] * sc; out[2] = p[2] * sc; return out;
}
const tesAngs = (T, extra = 0) => [T * 0.31 + extra, T * 0.19, T * 0.41 + extra * 0.5, T * 0.23, T * 0.37, T * 0.29];
function makeTesseract(o = {}) {
  const g = new THREE.Group();
  const gl = new Glow(48, {parent: g, px: o.px ?? 1.6, world: o.world ?? 0.03, halo: 1.5, haloGain: 0.35, inPortal: o.inPortal, fog: o.fog});
  g.userData = {gl, P: TES_V.map(() => [0, 0, 0])};
  (o.parent ?? S).add(g);
  return g;
}
// edges in `c`, corners as small stars; inner (far in the 4th dimension) edges are dimmer
function updateTesseract(tes, angs, c, gain = 1.6, nodeGain = 2.5) {
  const {gl, P} = tes.userData;
  TES_V.forEach((v, i) => project4(v, angs, 3.1, P[i]));
  TES_E.forEach((e, i) => {
    const a = P[e[0]], b = P[e[1]];
    gl.seg(i, a[0], a[1], a[2], b[0], b[1], b[2]);
    const size = (Math.hypot(a[0], a[1], a[2]) + Math.hypot(b[0], b[1], b[2])) * 0.5;      // 1.3 (inner cube) .. 2.6 (outer)
    gl.col(i, c, gain * (0.35 + 0.65 * sstep(1.1, 2.4, size)));
  });
  for (let i = 0; i < 16; i++) { gl.dot(32 + i, P[i][0], P[i][1], P[i][2]); gl.col(32 + i, WHITE, nodeGain, 2.6); }
  gl.flush();
}

// ---------- stars and dust with depth: points that wrap along the flight axis; fast flight stretches them ----------
function wrapZ(z0, dist, depth, camZ = 0, near = 8) { const span = Math.max(1, depth - near); let u = (z0 + dist) % span; if (u < 0) u += span; return camZ - near - u; }
function makeStars(n, rad, depth, seed, o = {}) {
  const r = rng(seed), gl = new Glow(n, {px: o.px ?? 1.5, halo: 1.3, haloGain: 0.45, world: o.world ?? 0, fog: o.fog, order: 2, inPortal: o.inPortal});
  const base = [], tints = o.tints ?? [WHITE, WHITE, ICE, ICE, CYAN, VIO];
  for (let i = 0; i < n; i++) {
    const a = r() * TAU, d = rad[0] + (rad[1] - rad[0]) * Math.sqrt(r());
    const c = tints[Math.floor(r() * tints.length)], m = 0.25 + 1.5 * Math.pow(r(), 2.4), w = 0.6 + 1.3 * Math.pow(r(), 3);
    base.push([Math.cos(a) * d, Math.sin(a) * d, r() * depth, m, w, r() * TAU, c]);
  }
  return {gl, base, depth, n};
}
function updateStars(st, T, dist, streak = 0, camZ = 0, gain = 1, near = 10) {
  const {gl, base, depth} = st, edge = depth * 0.12;
  for (let i = 0; i < base.length; i++) {
    const b = base[i], z = wrapZ(b[2], dist, depth, camZ, near), dz = camZ - z;
    const fade = sstep(depth, depth - edge, dz) * sstep(near, near + edge * 0.3, dz);
    const tw = 0.75 + 0.25 * Math.sin(T * (1.3 + (i % 7) * 0.31) + b[5]);
    gl.seg(i, b[0], b[1], z, b[0], b[1], z - streak);
    gl.col(i, b[6], b[3] * fade * tw * gain, b[4]);
  }
  gl.flush();
}

// ---------- light itself: a flare (glow, a horizontal streak, slow rays) that always faces the camera ----------
const FLARE_VERT = "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }";
const FLARE_FRAG = /* glsl */`
uniform vec3 uCol; uniform float uI, uStreak, uRays, uRot; varying vec2 vUv;
void main(){
  vec2 p = vUv * 2.0 - 1.0; float r = length(p);
  float fall = smoothstep(1.0, 0.25, r);
  float g = exp(-r * r * 30.0) + 0.045 / (r * r * 30.0 + 0.09);
  float st = exp(-abs(p.y) * 70.0) * exp(-abs(p.x) * 3.2) * uStreak * 0.6;
  float a = atan(p.y, p.x);
  float rays = (pow(abs(sin(a * 3.0 + uRot)), 18.0) + 0.6 * pow(abs(sin(a * 5.0 - uRot * 1.7 + 1.0)), 26.0)) * exp(-r * 3.4) * uRays;
  gl_FragColor = vec4(uCol * uI * (g + st + rays) * fall, 1.0);
}`;
function makeFlare(size, o = {}) {
  const m = new THREE.ShaderMaterial({uniforms: {uCol: {value: new THREE.Color(1, 1, 1)}, uI: {value: 1}, uStreak: {value: o.streak ?? 0.8}, uRays: {value: o.rays ?? 0.25}, uRot: {value: 0}},
    vertexShader: FLARE_VERT, fragmentShader: FLARE_FRAG, transparent: true, depthWrite: false, depthTest: o.depthTest ?? true, blending: THREE.AdditiveBlending});
  if (o.inPortal) portalOnly(m);
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(size, size), m); mesh.renderOrder = o.order ?? 3; mesh.frustumCulled = false;
  (o.parent ?? S).add(mesh);
  return mesh;
}
function setFlare(f, c, i, rot = 0, scale = 1) { const u = f.material.uniforms; u.uCol.value.copy(c); u.uI.value = i; u.uRot.value = rot; f.scale.setScalar(scale); f.quaternion.copy(C.quaternion); }

// ---------- rings of light that spread from a hit (booms, big drums) ----------
function makeShocks(n, seg = 96) { const a = []; for (let i = 0; i < n; i++) a.push(Glow.from(circlePts(seg, 1), {px: 1.4, world: 0.02, halo: 2.0, haloGain: 0.4})); return a; }
// one ring per recent hit of `name`: it grows with age and fades
function updateShocks(shocks, name, T, c, o = {}) {
  const h = AU.hits[name], last = h ? lastIdx(h.t, T) : -1;
  shocks.forEach((s, k) => {
    const j = last - k, age = j >= 0 ? T - h.t[j] : 1e9, life = o.life ?? 3.5;
    if (age > life || (o.only && !o.only(h.t[j]))) { s.mesh.visible = false; return; }
    s.mesh.visible = true;
    const u = age / life, r = (o.r0 ?? 3) + (o.r1 ?? 70) * (1 - Math.pow(1 - u, 2.2));
    s.mesh.scale.setScalar(r); s.mesh.position.copy(o.at ?? V3.set(0, 0, 0)); if (o.face) s.mesh.quaternion.copy(C.quaternion);
    s.mat.uniforms.uWorld.value = 0.012 + 0.03 * u;
    s.tint(c, (o.gain ?? 3) * Math.pow(1 - u, 1.6) * Math.min(h.g[j], 1.3));
  });
}

// ---------- the melody as a line of light: the hook's pitch drawn through time ----------
let GLIDE = null;
// pitch (MIDI) of `name` at time T, gliding between notes, and how loud it is
function melody(name, T, glide = 0.07) {
  glide = GLIDE ?? glide;
  const n = AU.notes[name], i = n ? lastIdx(n.t, T) : -1;
  if (i < 0) return [n && n.p.length ? n.p[0] : 69, 0];
  const age = T - n.t[i], prev = i > 0 && n.t[i] - (n.t[i - 1] + n.d[i - 1]) < 0.4 ? n.p[i - 1] : n.p[i];
  const p = mix(prev, n.p[i], sstep(0, glide, age));
  const amp = age < n.d[i] ? clamp(age / 0.05) : Math.exp(-(age - n.d[i]) / 0.45);
  return [p, amp];
}

// ---------- camera ----------
function setCam(x, y, z, lx, ly, lz, roll = 0, fov = 55) {
  C.position.set(x, y, z); C.up.set(Math.sin(roll), Math.cos(roll), 0); C.lookAt(lx, ly, lz);
  if (Math.abs(C.fov - fov) > 1e-3) { C.fov = fov; C.updateProjectionMatrix(); }
  C.updateMatrixWorld();
}

// ---------- the finish: tone curve, grade, fringe, vignette, grain, flash and fade ----------
const FIN = {
  uniforms: {tDiffuse: {value: null}, uRes, uExp: {value: 1}, uCA: {value: 0.6}, uVig: {value: 0.55}, uGrain: {value: 0.02}, uSeed: {value: 0}, uFade: {value: 1},
    uFlash: {value: 0}, uFlashCol: {value: new THREE.Color(1, 1, 1)}, uSat: {value: 1.08}, uLift: {value: new THREE.Color(0, 0, 0)}, uGainC: {value: new THREE.Color(1, 1, 1)}},
  vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
  fragmentShader: /* glsl */`
uniform sampler2D tDiffuse; uniform vec2 uRes; uniform float uExp, uCA, uVig, uGrain, uSeed, uFade, uFlash, uSat; uniform vec3 uFlashCol, uLift, uGainC;
varying vec2 vUv;
vec3 aces(vec3 x){ return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }
float hash(vec2 p){ vec3 q = fract(vec3(p.xyx) * 0.1031); q += dot(q, q.yzx + 33.33); return fract((q.x + q.y) * q.z); }
void main(){
  vec2 p = vUv - 0.5; p.x *= uRes.x / uRes.y * 0.72;
  float r2 = dot(p, p);
  vec2 ca = (vUv - 0.5) * r2 * uCA * 0.012;
  vec3 c = vec3(texture2D(tDiffuse, vUv - ca).r, texture2D(tDiffuse, vUv).g, texture2D(tDiffuse, vUv + ca).b);
  c = c * uExp + uFlashCol * uFlash;
  c *= 1.0 - uVig * smoothstep(0.08, 0.62, r2);
  c = aces(c);
  float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
  c = mix(vec3(l), c, uSat);
  c = c * uGainC + uLift * (1.0 - c);
  c = mix(c * 12.92, 1.055 * pow(max(c, 0.0), vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
  float g = hash(gl_FragCoord.xy + vec2(uSeed * 17.0, uSeed * 31.0)) + hash(gl_FragCoord.yx + vec2(uSeed * 7.0, 11.0)) - 1.0;
  c += g * uGrain * (1.0 - 0.6 * l);
  gl_FragColor = vec4(clamp(c, 0.0, 1.0) * uFade, 1.0);
}`,
};
// one call per frame: exposure, bloom, flash (0..), fade (1 = picture, 0 = black), grade
function finish(T, o = {}) {
  const u = fin.uniforms;
  const fl = o.flash ?? 0;
  u.uExp.value = (o.exp ?? 1) * (1 + 1.6 * fl); u.uFade.value = o.fade ?? 1; u.uFlash.value = 0.07 * fl; u.uFlashCol.value.copy(o.flashCol ?? WHITE);
  u.uSat.value = o.sat ?? 1.08; u.uVig.value = o.vig ?? 0.55; u.uCA.value = o.ca ?? 0.6; u.uGrain.value = o.grain ?? 0.02;
  u.uLift.value.copy(o.lift ?? BLACK); u.uGainC.value.copy(o.gain ?? ONE);
  u.uSeed.value = Math.round(T * 30) % 251;
  bloom.strength = o.bloom ?? 0.6; bloom.radius = o.radius ?? 0.55; bloom.threshold = o.threshold ?? 0.9;
}
const BLACK = new THREE.Color(0, 0, 0), ONE = new THREE.Color(1, 1, 1);
// the flash of a downbeat: the booms that open sections
const boomFlash = (T, decay = 0.5) => env("boom", T, decay);

// ====================================================================================================
// the scenes
// ====================================================================================================
const MODES = {};

// ---- dawn (bars 0-8): one small light in a very large dark; the title; a far men's choir, then a clock starts ----
MODES.dawn = {
  build() {
    O.sky = makeSky(3);
    O.stars = makeStars(900, [14, 260], 620, 11);
    O.dust = makeStars(160, [3, 40], 160, 29, {px: 3.2, tints: [ICE, BLUE, WHITE]});
    O.tes = makeTesseract({world: 0.05}); O.tes.position.set(0, 0, -150); O.tes.scale.setScalar(6.5);
    O.flare = makeFlare(1, {streak: 1.0, rays: 0.3}); O.flare.position.copy(O.tes.position);
    O.shocks = makeShocks(3);
    O.glints = new Glow(60, {px: 1.6, halo: 1.6, haloGain: 0.5});
    const marks = []; for (let i = 0; i < 16; i++) { const a = (i / 16) * TAU; marks.push(Math.sin(a) * 15, Math.cos(a) * 15, 0, Math.sin(a) * (i % 4 ? 16.2 : 17.4), Math.cos(a) * (i % 4 ? 16.2 : 17.4), 0); }
    O.dial = Glow.from(marks, {px: 1.3, world: 0.12}); O.dial.mesh.position.copy(O.tes.position);
  },
  frame(T, t) {
    const p = clamp(t / (8 * BAR)), boom = env("boom", T, 1.4), horn = noteAmp("horn", T, 0.5, 1.2);
    const cz = -62 * ease(p * 0.96);
    setCam(Math.sin(T * 0.11) * 2.4, 1.0 + Math.cos(T * 0.09) * 1.2, cz, 0, 0, -150, 0.03 * Math.sin(T * 0.13), 50);
    skyTurn(O.sky.u, T);
    skyColors(O.sky, hx(0x010207), hx(0x051a33), lerpC(hx(0x1c6a8c), hx(0x4a8a9a), horn), 0.32 + 0.2 * p);
    skyLight(O.sky, 1, V3.set(0.05, 0.02, -1), lerpC(ICE, AMBER, horn * 0.5), 0.03 + 0.10 * boom + 0.05 * horn, 14);
    skyLight(O.sky, 2, V3.set(-0.6, 0.5, -0.4), BLUE, 0.02 + 0.02 * p, 3);
    updateStars(O.stars, T, 6 * t, 0.0, cz, 1);
    updateStars(O.dust, T, 3 * t, 0.0, cz, 0.12, 4);
    updateTesseract(O.tes, tesAngs(T * 0.35 + 2), lerpC(ICE, WHITE, boom), 1.1 + 2.2 * boom + 0.5 * horn, 2.2 + 3 * boom);
    setFlare(O.flare, lerpC(ICE, AMBER, horn * 0.6), 0.5 + 1.6 * boom + 0.6 * horn, T * 0.05, 26 + 10 * boom);
    updateShocks(O.shocks, "boom", T, ICE, {at: O.tes.position, r0: 6, r1: 150, life: 6, gain: 2.2, face: true});
    // a clock around the light: every tick lights the next mark
    const ticks = AU.hits.tick, ti = lastIdx(ticks.t, T), te = env("tick", T, 0.22);
    for (let i = 0; i < 16; i++) { const back = ti < 0 ? 99 : ((ti - i) % 16 + 16) % 16; O.dial.col(i, ICE, ti < 0 ? 0 : 0.18 + (back < 5 ? te * Math.pow(0.5, back) * 3.2 : 0)); }
    O.dial.flush(false, true); O.dial.mesh.quaternion.copy(C.quaternion);
    // every note of the far choir (the track named trumpet) lights a star for a while, higher notes higher up
    // (v7 sings it two octaves under v6's trumpet: 46 here was 70, so the stars stay where they were)
    const bells = AU.notes.call, bi = lastIdx(bells.t, T);
    for (let k = 0; k < 12; k++) {
      const j = bi - k, base = k * 5;
      if (j < 0 || T - bells.t[j] > 5) { for (let q = 0; q < 5; q++) O.glints.hide(base + q); continue; }
      const age = T - bells.t[j], e = Math.exp(-age / 1.6) * clamp(age / 0.08), a = hash1(j, 1) * TAU, rr = 26 + 30 * hash1(j, 2);
      const x = Math.cos(a) * rr * 1.5, y = (bells.p[j] - 46) * 2.6 + Math.sin(a) * 8, z = -150 + 30 * (hash1(j, 3) - 0.5), s = 2.2 * e + 0.4;
      O.glints.dot(base, x, y, z); O.glints.col(base, WHITE, 5 * e, 2.4);
      O.glints.seg(base + 1, x - s * 2, y, z, x + s * 2, y, z); O.glints.seg(base + 2, x, y - s, z, x, y + s, z);
      O.glints.seg(base + 3, x - s * 0.5, y - s * 0.5, z, x + s * 0.5, y + s * 0.5, z); O.glints.seg(base + 4, x - s * 0.5, y + s * 0.5, z, x + s * 0.5, y - s * 0.5, z);
      for (let q = 1; q < 5; q++) O.glints.col(base + q, ICE, (q < 3 ? 1.6 : 0.7) * e, 0.7);
    }
    O.glints.flush();
    finish(T, {exp: 1.0, bloom: 0.7, fade: sstep(0, 2.2, t), flash: 0, lift: hx(0x020409), gain: new THREE.Color(0.96, 1.0, 1.06), vig: 0.7});
    const a = sstep(BAR * 0.9, BAR * 1.5, t) * (1 - sstep(BAR * 3.5, BAR * 4.2, t));
    titleEl.style.opacity = a.toFixed(3); titleEl.style.display = a > 0.002 ? "block" : "none";
    titleEl.style.letterSpacing = "0";
    titleEl.firstChild.style.letterSpacing = (0.42 + 0.06 * sstep(BAR * 0.9, BAR * 4.2, t)).toFixed(4) + "em";
  },
};

// ---- shared pieces of the scenes ----
// notes of `name` as star glints: each note lights a small four-pointed star for a while, higher notes higher up
function updateGlints(gl, name, T, o = {}) {
  const ns = AU.notes[name], bi = ns ? lastIdx(ns.t, T) : -1, n = o.n ?? 12, life = o.life ?? 5, c = o.c ?? ICE;
  for (let k = 0; k < n; k++) {
    const j = bi - k, base = k * 5;
    if (j < 0 || T - ns.t[j] > life) { for (let q = 0; q < 5; q++) gl.hide(base + q); continue; }
    const age = T - ns.t[j], e = Math.exp(-age / (life * 0.32)) * clamp(age / (o.rise ?? 0.02)), P = o.place(j, ns.p[j]), s = (o.size ?? 2.2) * (e + 0.2);
    const x = P[0], y = P[1], z = P[2];
    gl.dot(base, x, y, z); gl.col(base, WHITE, (o.gain ?? 5) * e, 2.4);
    gl.seg(base + 1, x - s * 2, y, z, x + s * 2, y, z); gl.seg(base + 2, x, y - s, z, x, y + s, z);
    gl.seg(base + 3, x - s * 0.5, y - s * 0.5, z, x + s * 0.5, y + s * 0.5, z); gl.seg(base + 4, x - s * 0.5, y + s * 0.5, z, x + s * 0.5, y - s * 0.5, z);
    for (let q = 1; q < 5; q++) gl.col(base + q, c, (q < 3 ? 1.6 : 0.7) * e * (o.gain ?? 5) / 5, 0.7);
  }
  gl.flush();
}
// a field of crystals along the flight axis
function makeField(n, rad, depth, seed, pal, o = {}) {
  const r = rng(seed), list = [];
  for (let i = 0; i < n; i++) {
    const a = r() * TAU, d = rad[0] + r() * (rad[1] - rad[0]);
    const g = crystal(KINDS[i % (o.kinds ?? 3)], pal[i % pal.length], pal[(i + 1) % pal.length], {gain: o.gain ?? 1.5, inPortal: o.inPortal, world: o.world ?? 0.04});
    g.userData.f = {x: Math.cos(a) * d, y: Math.sin(a) * d * (o.flat ?? 1), z0: r() * depth, s: (o.s0 ?? 0.5) + r() * (o.s1 ?? 1.6), spin: 0.12 + r() * 0.5, band: i % 16, pulse: i % 2 === 0, ph: r() * TAU};
    list.push(g);
  }
  return {list, depth};
}
function updateField(f, T, dist, camZ = 0, kgain = 1, gain = 1, near = 14) {
  const k = kick(T) * kgain, edge = f.depth * 0.15;
  f.list.forEach((g) => {
    const u = g.userData.f, z = wrapZ(u.z0, dist, f.depth, camZ, near), dz = camZ - z;
    g.position.set(u.x, u.y, z); g.scale.setScalar(u.s);
    g.rotation.set(T * u.spin + u.ph, T * u.spin * 1.35, u.ph);
    lightCrystal(g, u.pulse ? k : 0.25 * band(T, u.band), gain * sstep(f.depth, f.depth - edge, dz) * sstep(near, near + 10, dz));
  });
}
// the corridor: a twisting truss of hexagons joined by struts, wrapped along the flight axis
function makeLattice(N = 14, spacing = 22, radius = 11, o = {}) {
  const gl = new Glow(N * 18, {px: 1.2, world: o.world ?? 0.05, halo: 1.5, haloGain: 0.3, max: 4, inPortal: o.inPortal});
  return {gl, N, spacing, radius, depth: N * spacing, twist: o.twist ?? Math.PI / 9};
}
// cellGain(i, depthAhead) -> brightness of a cell; struts are dimmer than the hexagons
function updateLattice(lat, T, dist, camZ, c, cellGain, strut = 0.45) {
  const {gl, N, spacing, radius, depth, twist} = lat;
  const turn = Math.floor(dist / depth);
  for (let i = 0; i < N; i++) {
    const zc = wrapZ(i * spacing, dist, depth, camZ, 0), ahead = camZ - zc;
    const lap = Math.floor((i * spacing + dist) / depth), rot = (i - lap * N) * twist, g = cellGain(i, ahead) * sstep(depth, depth * 0.75, ahead) * sstep(-2, 6, ahead);
    for (let k = 0; k < 6; k++) {
      const a0 = rot + (k / 6) * TAU, a1 = rot + ((k + 1) / 6) * TAU, b0 = a0 - twist, b1 = a1 - twist, j = i * 18 + k * 3, zn = zc + spacing;
      const x0 = Math.cos(a0) * radius, y0 = Math.sin(a0) * radius;
      gl.seg(j, x0, y0, zc, Math.cos(a1) * radius, Math.sin(a1) * radius, zc); gl.col(j, c, g);
      // struts to the hexagon behind this one (nearer the camera)
      const near = ahead > spacing * 0.5 ? 1 : 0;
      gl.seg(j + 1, x0, y0, zc, Math.cos(b0) * radius, Math.sin(b0) * radius, zn); gl.col(j + 1, c, g * strut * near);
      gl.seg(j + 2, x0, y0, zc, Math.cos(b1) * radius, Math.sin(b1) * radius, zn); gl.col(j + 2, c, g * strut * near * 0.6);
    }
  }
  gl.flush();
}
// the megastructure: great rings turning slowly about one centre, with marks like an instrument's scale
const RING_R = [34, 70, 118, 186, 280];
function makeRings(o = {}) {
  const g = new THREE.Group(), rings = [];
  RING_R.forEach((r, k) => {
    const h = new THREE.Group(), pts = circlePts(160, r);
    const n = 24 + k * 12; for (let i = 0; i < n; i++) { const a = (i / n) * TAU, r1 = r * (i % 6 === 0 ? 1.06 : 1.03); pts.push(Math.cos(a) * r, Math.sin(a) * r, 0, Math.cos(a) * r1, Math.sin(a) * r1, 0); }
    pts.push(...circlePts(160, r * 0.985));
    const gl = Glow.from(pts, {parent: h, px: 1.3, world: r * 0.004, halo: 1.5, haloGain: 0.35, max: 5, inPortal: o.inPortal});
    g.add(h); rings.push({h, gl, r});
  });
  S.add(g);
  return {g, rings};
}
function updateRings(m, T, c, gain, spin = 1) {
  m.rings.forEach((q, k) => {
    q.h.rotation.set(0.5 + k * 0.55 + T * 0.021 * spin * (k % 2 ? -1 : 1), k * 0.9 + T * 0.017 * spin, T * 0.03 * spin * (k % 2 ? 1 : -1));
    q.gl.tint(typeof c === "function" ? c(k) : c, typeof gain === "function" ? gain(k) : gain);
  });
}
// the ostinato's sixteenths: 1 on an accent of its 3+3+2 figure, less on the notes between
const OST_ACC = [1, 0.3, 0.3, 1, 0.3, 0.3, 1, 0.3, 1, 0.3, 0.3, 1, 0.3, 0.3, 1, 0.3];
function ostEnv(T, decay = 0.07) { if (T < 0) return 0; const k = Math.floor(T / S16 + 1e-6); return OST_ACC[k % 16] * Math.exp(-(T - k * S16) / decay); }
// the gate of the groove's supersaws (X..x..x.X..x..x.)
function gateEnv(T) { const k = Math.floor(T / S16 + 1e-6), ph = T / S16 - k; return [0, 3, 6, 8, 11, 14].includes(k % 16) ? (ph < 0.5 ? 1 : Math.exp(-(ph - 0.5) * 6)) : 0.1; }

// ---- pulse (bars 8-24): the ostinato; a corridor of cells lights up note by note, then opens onto great rings ----
MODES.pulse = {
  build() {
    O.sky = makeSky(7);
    O.stars = makeStars(900, [24, 300], 700, 13);
    O.dust = makeStars(180, [2.5, 30], 150, 31, {px: 3.0, tints: [ICE, BLUE, WHITE]});
    O.lat = makeLattice(14, 22, 11);
    O.rings = makeRings();
    O.tes = makeTesseract({world: 0.05}); O.rings.g.add(O.tes); O.tes.scale.setScalar(8);
    O.flare = makeFlare(1, {streak: 1.2, rays: 0.5});
    O.shocks = makeShocks(3, 128);
  },
  frame(T, t) {
    const tt = T - 8 * BAR, L = 16 * BAR, p = clamp(tt / L);
    const dist = 26 * tt + 25 * tt * tt / L, D = (26 * L + 25 * L) - dist + 6;             // distance to the rings' centre
    const k = kick(T), taiko = env("taiko", T, 0.45), boom = env("boom", T, 1.2), horn = noteAmp("horn", T, 0.5, 1.0), swell = sstep(0.5, 1, p), lv = level(T);
    const open = sstep(0.44, 0.6, p), rise = Math.sin(Math.PI * sstep(0.47, 0.97, p));                  // out of the corridor, up, and down again
    const cy = 1.2 * Math.sin(T * 0.21) + 46 * rise, cx = 1.6 * Math.sin(T * 0.17) + 20 * rise;
    O.rings.g.position.set(0, 0, -D);
    setCam(cx, cy, 0, cx * 0.3, cy * 0.25, -Math.max(D, 60), 0.05 * Math.sin(T * 0.19) + 0.12 * rise, 56 + 6 * swell);
    skyTurn(O.sky.u, T);
    skyColors(O.sky, hx(0x010209), hx(0x08133c), lerpC(hx(0x2a48b8), hx(0x5a58c8), swell), 0.3 + 0.25 * swell + 0.1 * lv);
    skyLight(O.sky, 1, V3.set(0, 0, -1), lerpC(ICE, AMBER, swell), 0.03 + 0.10 * swell + 0.08 * horn + 0.1 * boom, 9);
    const th = AU.hits.taiko, ti = lastIdx(th.t, T);
    skyLight(O.sky, 2, V3.set(Math.cos(ti * 2.4) * 0.8, Math.sin(ti * 1.7) * 0.5, -0.7), lerpC(VIO, ICE, hash1(ti)), 0.22 * taiko, 5);
    updateStars(O.stars, T, dist * 0.5, 0.2 + 2.2 * p * p, 0, 1);
    updateStars(O.dust, T, dist * 0.8, 0.3 + 1.5 * p, 0, 0.12, 3);
    // the corridor: light runs down it with every note of the ostinato (later cells light later)
    const og = sstep(0, 0.25, p) * 0.9 + 0.5;
    updateLattice(O.lat, T, dist, 0, lerpC(BLUE, ICE, 0.35 + 0.4 * p), (i, ahead) => (1 - open) * (0.16 + 0.12 * p + og * 2.2 * ostEnv(tt - ahead / 420) + 1.2 * taiko * Math.exp(-ahead / 90)));
    O.lat.gl.mesh.visible = open < 0.999;
    // the rings: far and small at first, then enormous
    const far = sstep(1500, 500, D);
    updateRings(O.rings, T, (q) => lerpC(q % 2 ? ICE : BLUE, AMBER, swell * (q === 0 ? 0.8 : 0.35)), (q) => (0.35 + 0.5 * far + 0.5 * swell) * (1 + 1.2 * k) * (1 + 0.6 * taiko) * (q === 0 ? 1.3 : 1));
    updateTesseract(O.tes, tesAngs(T * 0.4 + 5), lerpC(ICE, GOLD, swell), 1.4 + 1.5 * k + taiko, 3 + 2 * k);
    O.flare.position.copy(O.rings.g.position);
    setFlare(O.flare, lerpC(ICE, AMBER, swell * 0.8), 0.45 + 0.5 * swell + 0.4 * horn + 0.8 * boom + 0.5 * k, T * 0.04, 30 + 26 * swell + D * 0.05);
    updateShocks(O.shocks, "boom", T, lerpC(ICE, AMBER, swell), {at: O.rings.g.position, r0: 10, r1: 330, life: 5, gain: 2.5, face: true});
    const cres = sstep(15 * BAR, 16 * BAR, tt);
    finish(T, {exp: 1.0 + 0.15 * swell + 0.25 * cres * cres, bloom: 0.6 + 0.15 * swell, flash: 0.8 * Math.exp(-tt / 0.35) + 0.4 * env("boom", T, 0.3) * sstep(0.2, 0.6, p) + 1.2 * Math.pow(cres, 8),
      flashCol: lerpC(ICE, WHITE, 0.5), lift: hx(0x020309), gain: new THREE.Color(0.97, 1.0, 1.05), vig: 0.65});
  },
};

// ---- groove 1 (bars 24-32): the mirror corridor. We fly between two huge parallel planes of glass; each mirror
//      shows another copy of the flight, a little later, turned a little and shifted in colour, so the parallel
//      realities recede sideways to infinity. Wireframe solids float through all of them: on each kick they split
//      into copies that drift apart (brightness, never zoom), the gated chords make the mirror seams flash, and the
//      chords (and the choir, where it sings) light the solids from inside. In the last two bars the seams fold
//      together into one solid that recedes to where 04_groove2's portal opens. ----
const POLY = [6, 8, 5, 6];                      // the sides of the drop's rings (updateTunnel)
const MC = {a: 13, K: 4, depth: 300, near: 9, H: 42, lag: 0.075, v: 40};
const MC_PAL = [ICE, CYAN, BLUE, INDIGO, VIO, MAG, ROSE, ROSE];
const MC_KINDS = ["ico", "octa", "dodeca", "tetra", "cube", "ico", "dodeca", "octa", "ico", "tetra", "dodeca", "cube"];
const MC_M = new THREE.Matrix4(), MC_E = new THREE.Euler(), MC_V = new THREE.Vector3();
// the gate of the groove's chords: its hit times are on 16ths 0 3 6 8 11 14 of every bar
const GATE_STEPS = [0, 3, 6, 8, 11, 14];
function gateAge(T) { const k = Math.floor(T / S16 + 1e-6); for (let back = 0; back < 16; back++) { const j = k - back; if (GATE_STEPS.includes(((j % 16) + 16) % 16)) return {age: T - j * S16, acc: ((j % 16) + 16) % 16 === 0 || ((j % 16) + 16) % 16 === 8 ? 1 : 0.7}; } return {age: 9, acc: 0}; }
// the age of the latest kick (and its number) at song time T
function kickAge(T) { const h = AU.hits.kick, j = h ? lastIdx(h.t, T) : -1; return j < 0 ? {age: 99, j: -1, g: 0} : {age: T - h.t[j], j, g: h.g[j]}; }
// the inner light of the solids: a swell on every chord (two bars each), the choir's notes where it sings, the middle of the spectrum
function innerLight(T) {
  const c = 2 * BAR, age = T - Math.floor(T / c + 1e-6) * c;
  return 0.3 + 0.75 * sstep(0, 0.9, age) * Math.exp(-age / 2.6) + 1.3 * noteAmp("call", T, 0.3, 1.2) + 0.5 * band(T, 7);
}
// one wireframe solid's edges into a Glow, from index i; returns the next free index
function mcSolid(gl, i, s, Tk, pos, scale, c, m, w = 1) {
  if (s.kind === "tes") {
    const P = s.P, angs = tesAngs(Tk * 0.45 + s.ph);
    TES_V.forEach((v, q) => project4(v, angs, 3.1, P[q]));
    for (const e of TES_E) {
      const a = P[e[0]], b = P[e[1]], size = (Math.hypot(a[0], a[1], a[2]) + Math.hypot(b[0], b[1], b[2])) * 0.5;
      gl.seg(i, pos.x + a[0] * scale, pos.y + a[1] * scale, pos.z + a[2] * scale, pos.x + b[0] * scale, pos.y + b[1] * scale, pos.z + b[2] * scale);
      gl.col(i++, c, m * (0.35 + 0.65 * sstep(1.1, 2.4, size)), w);
    }
    return i;
  }
  MC_M.makeRotationFromEuler(MC_E.set(Tk * s.spin + s.ph, Tk * s.spin * 1.35, s.ph)).scale(MC_V.set(scale, scale, scale)).setPosition(pos);
  const E = EDGE[s.kind], el = MC_M.elements;
  for (let q = 0; q < E.length; q += 6) {
    const ax = E[q], ay = E[q + 1], az = E[q + 2], bx = E[q + 3], by = E[q + 4], bz = E[q + 5];
    gl.seg(i, el[0] * ax + el[4] * ay + el[8] * az + el[12], el[1] * ax + el[5] * ay + el[9] * az + el[13], el[2] * ax + el[6] * ay + el[10] * az + el[14],
      el[0] * bx + el[4] * by + el[8] * bz + el[12], el[1] * bx + el[5] * by + el[9] * bz + el[13], el[2] * bx + el[6] * by + el[10] * bz + el[14]);
    gl.col(i++, c, m, w);
  }
  return i;
}
// the glass of a mirror: almost nothing, a faint sheen that runs along it, brighter where we look along it
const GLASS_VERT = "varying vec3 vW; varying vec3 vV; void main(){ vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; vec4 mv = viewMatrix * w; vV = mv.xyz; gl_Position = projectionMatrix * mv; }";
const GLASS_FRAG = /* glsl */`
uniform vec3 uCol, uCol2; uniform float uBase, uSheen, uZs, uH, uFar; varying vec3 vW; varying vec3 vV;
void main(){
  float d = -vV.z;
  float fade = smoothstep(uFar, uFar * 0.35, d) * smoothstep(2.0, 14.0, d);
  float edge = smoothstep(uH, uH * 0.55, abs(vW.y));
  float s1 = (vW.z - uZs) / 26.0, s2 = (vW.z - uZs + 140.0) / 40.0;
  float sheen = exp(-s1 * s1) + 0.45 * exp(-s2 * s2);
  float grad = 0.6 + 0.4 * sin(vW.y * 0.09 + vW.z * 0.004);
  vec3 c = mix(uCol, uCol2, 0.5 + 0.5 * sin(vW.z * 0.011));
  gl_FragColor = vec4(c * (uBase * grad + uSheen * sheen) * fade * edge, 1.0);
}`;
function makeGlass(x, far) {
  const m = new THREE.ShaderMaterial({uniforms: {uCol: {value: new THREE.Color()}, uCol2: {value: new THREE.Color()}, uBase: {value: 0.03}, uSheen: {value: 0.1}, uZs: {value: -60}, uH: {value: MC.H}, uFar: {value: far}},
    vertexShader: GLASS_VERT, fragmentShader: GLASS_FRAG, transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide});
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(760, MC.H * 2), m);
  mesh.rotation.y = Math.PI / 2; mesh.position.set(x, 0, -360); mesh.renderOrder = 1; mesh.frustumCulled = false; S.add(mesh);
  return mesh;
}
// the solid the mirrors fold into: an icosahedron, its dual and a tesseract inside (edges in a flat list)
function foldTarget() {
  const out = [], ico = EDGE.ico, dod = EDGE.dodeca, k = 1 / 0.95;
  for (let q = 0; q < ico.length; q += 6) out.push(ico.slice(q, q + 6));
  for (let q = 0; q < dod.length; q += 6) out.push(dod.slice(q, q + 6).map((v) => v * 0.78 * k));
  const P = TES_V.map((v) => project4(v, [0.4, 0.3, 0.2, 0.1, 0.5, 0.3], 3.1, [0, 0, 0]).map((u) => u * 0.2));
  for (const e of TES_E) out.push([...P[e[0]], ...P[e[1]]]);
  return out;
}
MODES.groove1 = {
  build() {
    O.sky = makeSky(12);
    O.stars = makeStars(800, [22, 240], 520, 17, {tints: [WHITE, ICE, CYAN, VIO]});
    const r = rng(77);
    O.solids = [];
    for (let i = 0; i < 14; i++) {
      const kind = i < 12 ? MC_KINDS[i] : "tes", lane = (i % 7) / 6 - 0.5;
      const hero = i % 4 === 1, side = i % 2 ? 1 : -1;                                      // every fourth solid is a big one, off the flight path
      O.solids.push({kind, x: hero ? side * (6 + 3 * r()) : lane * 2 * (MC.a - 3.6) + (r() - 0.5) * 2.2, y: hero ? (r() - 0.5) * 14 + 4 * side : (r() - 0.5) * 26, z0: (i / 14) * MC.depth + r() * 12,
        s: kind === "tes" ? 1.0 + 0.4 * r() : hero ? 3.0 + 1.2 * r() : 1.1 + 1.2 * r(),
        spin: (0.18 + 0.35 * r()) * (r() < 0.5 ? -1 : 1), ph: r() * TAU, pal: Math.floor(r() * 2), P: TES_V.map(() => [0, 0, 0]), sx: r() * 2 - 1, sy: r() * 2 - 1});
    }
    O.dust = []; for (let i = 0; i < 46; i++) O.dust.push([(r() - 0.5) * 2 * (MC.a - 0.6), (r() - 0.5) * 60, r() * MC.depth, 0.3 + r() * 0.7]);
    // the realities: copy k of everything between the mirrors (k = 0 is ours), mirrored, turned and tinted
    O.real = [];
    for (let k = -MC.K; k <= MC.K; k++) {
      const g = new THREE.Group(); S.add(g);
      const gl = new Glow(1000, {parent: g, px: 1.25, world: 0.04, halo: 1.3, haloGain: 0.32, max: 4, fog: [150, 470]});
      const inner = new Glow(14 * 3, {parent: g, px: 6, world: 0.9, halo: 2.2, haloGain: 0.55, max: 26, fog: [150, 470]});
      O.real.push({k, g, gl, inner});
    }
    // the seams of the mirrors: the two real planes and their images, long lines along the flight and cross seams
    O.planes = []; for (let j = -MC.K - 1; j <= MC.K; j++) O.planes.push(j);
    O.NL = 7; O.NC = 22;
    O.seams = new Glow(O.planes.length * (O.NL + O.NC), {px: 1.2, world: 0.06, halo: 1.6, haloGain: 0.35, max: 5, fog: [170, 560]});
    O.glass = [-3, -1, 1, 3].map((m) => makeGlass(m * MC.a, m === -1 || m === 1 ? 420 : 300));
    O.target = foldTarget();
    O.flare = makeFlare(1, {streak: 1.4, rays: 0.4});
    O.core = makeFlare(1, {streak: 0.6, rays: 0.5});
  },
  frame(T, t) {
    const L = 8 * BAR, p = clamp(t / L), lv = level(T), clap = env("clap", T, 0.14);
    const fold = ease(clamp((t - 6 * BAR) / (1.75 * BAR))), open = 1 - fold, calm = 1 - ease(clamp((t - 5.5 * BAR) / (2 * BAR)));
    const dist = MC.v * t;
    // a slow, smooth sway down the middle; still at the end, looking at the solid
    const yaw = Math.sin(TAU * t / (11 * BAR) - 0.6);                                  // we look into one mirror, then the other
    setCam(-4.5 * yaw * calm + Math.sin(T * 0.31) * 0.8 * calm, 0.6 + Math.cos(T * 0.27) * 1.2 * calm, 0, 30 * yaw * calm, 0.3 * Math.sin(T * 0.23) * calm, -100, (0.05 * Math.sin(T * 0.17) - 0.04 * yaw) * calm, 64);
    skyTurn(O.sky.u, T, 2);
    skyColors(O.sky, hx(0x02010c), hx(0x150a48), hx(0x2a7fd0), 0.34 + 0.12 * lv);
    skyLight(O.sky, 1, V3.set(0, 0, -1), lerpC(CYAN, MAG, clap * 0.6), 0.07 + 0.1 * clap + 0.08 * fold, 8);
    skyLight(O.sky, 2, V3.set(0.7, 0.4, -0.5), VIO, 0.04, 3);
    updateStars(O.stars, T, dist * 1.1, 1.4, 0, 1);
    const gate = gateAge(T), gEnv = Math.exp(-gate.age / 0.16) * gate.acc, gWave = gate.age;
    // ---- the realities ----
    const delta = (0.055 + 0.025 * Math.sin(T * 0.21)) * open;
    O.real.forEach((R0) => {
      const k = R0.k, ak = Math.abs(k), Tk = T - ak * MC.lag, kk = kick(Tk), ka = kickAge(Tk), inner = innerLight(Tk);
      R0.g.position.set(2 * k * MC.a * open, 0, 0); R0.g.scale.set(k % 2 ? -1 : 1, 1, 1); R0.g.rotation.set(0, 0, k * delta);
      const dim = (k === 0 ? 1 : Math.pow(0.8, ak) * open) * (1 - 0.15 * fold * (k === 0 ? 0 : 1));
      R0.g.visible = dim > 0.004;
      if (!R0.g.visible) return;
      const gl = R0.gl; let i = 0, n = 0;
      const distK = MC.v * (t - ak * MC.lag);
      O.solids.forEach((s, si) => {
        const z = wrapZ(s.z0, distK, MC.depth, 0, MC.near), dz = -z;
        const fade = sstep(MC.depth, MC.depth * 0.8, dz) * sstep(MC.near, MC.near + 10, dz) * (1 - fold);
        const cA = MC_PAL[Math.min(MC_PAL.length - 1, s.pal + ak)], cB = MC_PAL[Math.min(MC_PAL.length - 1, s.pal + ak + 1)];
        const pos = V3b.set(s.x * (1 - 0.6 * fold), s.y * (1 - 0.6 * fold), z);
        const c = lc(cA, WHITE, 0.4 * kk), m = fade * (1.25 + 1.9 * kk) * (s.kind === "tes" ? 1.25 : 1);
        if (fade < 0.003) { n++; return; }
        i = mcSolid(gl, i, s, Tk, pos, s.s, c, m, 1);
        // on each kick the solid splits: two copies drift apart from it, fading
        if (ka.age < 1.4 && ka.j >= 0) {
          const e = ka.age, sep = s.s * 1.9 * (1 - Math.exp(-e / 0.24)), gf = Math.exp(-e / 0.42) * Math.min(ka.g, 1.25) * 0.75;
          const an = hash1(ka.j * 31 + si, 5) * TAU, ux = Math.cos(an), uy = Math.sin(an) * 0.8;
          const P1 = MC_V.set(pos.x + ux * sep, pos.y + uy * sep, pos.z).clone(), P2 = MC_V.set(pos.x - ux * sep, pos.y - uy * sep, pos.z).clone();
          const cg = lc(cB, WHITE, 0.25);
          i = mcSolid(gl, i, s, Tk + 0.15 * e, P1, s.s * 0.92, cg, fade * gf, 0.8);
          i = mcSolid(gl, i, s, Tk - 0.15 * e, P2, s.s * 0.92, cg, fade * gf, 0.8);
        }
        // the light inside it
        const ii = R0.inner;
        ii.dot(n, pos.x, pos.y, pos.z); ii.col(n, lc(cA, WHITE, 0.55), fade * inner * (0.42 + 0.5 * kk) * (k === 0 ? 1 : 0.6), s.s * 0.8); n++;
      });
      for (let q = n; q < R0.inner.max; q++) R0.inner.hide(q);
      // dust between the mirrors, moving with the flight
      for (const d of O.dust) {
        const z = wrapZ(d[2], distK * 1.2, MC.depth, 0, 4), dz = -z, f = sstep(MC.depth, MC.depth * 0.8, dz) * sstep(4, 12, dz) * (1 - fold);
        gl.seg(i, d[0], d[1], z, d[0], d[1], z - 0.9); gl.col(i++, MC_PAL[Math.min(7, 1 + ak)], 0.5 * d[3] * f, 0.8);
      }
      for (let q = i; q < gl.max; q++) gl.hide(q);
      gl.count(i); gl.flush(); R0.inner.flush();
      gl.tint(WHITE, dim); R0.inner.tint(WHITE, dim);
    });
    // ---- the mirrors: seams on every plane (the real ones and their images), flashing with the gate; then they fold into one solid ----
    const tgt = O.target, nT = tgt.length, Dt = mix(46, 92, ease(clamp((t - 6.9 * BAR) / (1.0 * BAR)))), rt = mix(15, 10.5, ease(clamp((t - 6.9 * BAR) / (1.0 * BAR))));
    MC_M.makeRotationFromEuler(MC_E.set(0.35 + T * 0.23, T * 0.31, 0.2 + T * 0.11)).scale(MC_V.set(rt, rt, rt)).setPosition(0, 0.5, -Dt);
    const el = MC_M.elements;
    const tx = (x, y, z, o) => { o[0] = el[0] * x + el[4] * y + el[8] * z + el[12]; o[1] = el[1] * x + el[5] * y + el[9] * z + el[13]; o[2] = el[2] * x + el[6] * y + el[10] * z + el[14]; };
    const A = [0, 0, 0], B = [0, 0, 0], kNow = kick(T), solidC = lc(lc(ICE, CYAN, 0.3), lc(ROSE, GOLD, 0.45), sstep(0.55, 1, fold));
    let i = 0;
    O.planes.forEach((j, pj) => {
      const x = (2 * j + 1) * MC.a * open, near = Math.abs(j + 0.5) - 0.5, pg = Math.pow(0.74, near) * (j === -1 || j === 0 ? 1.25 : 1);
      const pc = MC_PAL[Math.min(7, 1 + Math.round(near) + (pj % 2))];
      for (let q = 0; q < O.NL + O.NC; q++, i++) {
        let ax, ay, az, bx, by, bz, g;
        if (q < O.NL) {                                         // a long seam along the flight
          const y = (q / (O.NL - 1) - 0.5) * 2 * MC.H * 0.92;
          ax = x; ay = y; az = -14; bx = x; by = y; bz = -640;
          g = (q === 0 || q === O.NL - 1 ? 1.1 : 0.42) * (1 + 2.2 * gEnv);
        } else {                                                // a cross seam, rushing past; a light runs down the corridor on every gate
          const z = wrapZ((q - O.NL) * 26, dist, 26 * O.NC, 0, -6), ahead = -z, wave = Math.exp(-Math.pow((ahead - gWave * 330) / 28, 2)) * Math.exp(-gWave / 0.6) * gate.acc;
          ax = x; ay = -MC.H; az = z; bx = x; by = MC.H; bz = z;
          g = (0.26 + 1.5 * gEnv + 2.6 * wave) * sstep(26 * O.NC, 26 * O.NC * 0.7, ahead) * sstep(-6, 8, ahead) * (near < 0.5 ? 1 : 0.35);
        }
        // the fold: every seam flies to an edge of the solid ahead, one after the other
        const u = ease(clamp(fold * 1.7 - (((i * 7) % 61) / 61) * 0.7));
        if (u > 0) {
          const e = tgt[i % nT]; tx(e[0], e[1], e[2], A); tx(e[3], e[4], e[5], B);
          ax = mix(ax, A[0], u); ay = mix(ay, A[1], u); az = mix(az, A[2], u); bx = mix(bx, B[0], u); by = mix(by, B[1], u); bz = mix(bz, B[2], u);
          const dup = Math.ceil(O.seams.max / nT);
          g = mix(g * pg, (i % nT < 30 ? 1.7 : i % nT < 60 ? 1.1 : 0.9) * (1 + 1.5 * kNow) / Math.pow(dup, 0.75), u);
          O.seams.seg(i, ax, ay, az, bx, by, bz); O.seams.col(i, lc(pc, solidC, u), g, 1 + 0.5 * u);
        } else {
          O.seams.seg(i, ax, ay, az, bx, by, bz); O.seams.col(i, pc, g * pg, 1);
        }
      }
    });
    O.seams.flush();
    // the glass: a faint sheen that slides along with each gate
    O.glass.forEach((m, gi) => {
      const u = m.material.uniforms, near = gi === 1 || gi === 2;
      m.position.x = [-3, -1, 1, 3][gi] * MC.a * open;
      u.uCol.value.copy(near ? CYAN : VIO); u.uCol2.value.copy(near ? BLUE : MAG);
      u.uBase.value = (near ? 0.022 : 0.01) * open * (1 + 0.8 * gEnv); u.uSheen.value = (near ? 0.11 : 0.04) * open * (0.35 + 1.6 * gEnv);
      u.uZs.value = -10 - gWave * 330;
      m.visible = open > 0.01;
    });
    // far light down the corridor; the solid's heart at the end
    O.flare.position.set(0, 0, -330);
    setFlare(O.flare, lerpC(ICE, CYAN, 0.5), (0.7 + 0.6 * kNow + 0.4 * lv) * open, T * 0.1, 46);
    O.core.position.set(0, 0.5, -Dt);
    setFlare(O.core, lc(ROSE, GOLD, 0.5), sstep(0.3, 1, fold) * (0.5 + 0.6 * kNow + 0.4 * innerLight(T)), T * 0.06, 22 + 8 * fold);
    const end = sstep(7.55 * BAR, 8 * BAR, t);
    finish(T, {exp: 1.02, bloom: 0.72, flash: 1.0 * Math.exp(-t / 0.3) + 0.45 * Math.pow(end, 4), flashCol: lc(lerpC(ICE, WHITE, 0.6), GOLD, end), lift: hx(0x02020a), gain: new THREE.Color(0.97, 1.0, 1.06), ca: 0.9});
  },
};

// ---- more shared pieces ----
const lc = (a, b, u, m = 1) => a.clone().lerp(b, clamp(u)).multiplyScalar(m);      // a new colour (lerpC returns a shared one)
const ORIGIN = new THREE.Vector3(0, 0, 0);
// far points all around: stars with depth for scenes where the camera circles a centre
function makeShell(n, r0, r1, seed, o = {}) {
  const r = rng(seed), gl = new Glow(n, {px: o.px ?? 1.5, halo: 1.3, haloGain: 0.45, order: 2, inPortal: o.inPortal}), tints = o.tints ?? [WHITE, WHITE, ICE, GOLD, ROSE];
  for (let i = 0; i < n; i++) {
    const z = r() * 2 - 1, a = r() * TAU, q = Math.sqrt(1 - z * z), d = r0 + (r1 - r0) * Math.pow(r(), 0.7);
    gl.dot(i, Math.cos(a) * q * d, z * d * (o.flat ?? 1), Math.sin(a) * q * d);
    gl.col(i, tints[Math.floor(r() * tints.length)], 0.25 + 1.5 * Math.pow(r(), 2.4), 0.6 + 1.3 * Math.pow(r(), 3));
  }
  gl.flush();
  return gl;
}
// crystals on slow orbits about a centre
function makeSwarm(n, rad, seed, pal, o = {}) {
  const r = rng(seed), list = [];
  for (let i = 0; i < n; i++) {
    const g = crystal(KINDS[i % 5], pal[i % pal.length], pal[(i + 1) % pal.length], {gain: o.gain ?? 1.5, world: o.world ?? 0.06, inPortal: o.inPortal});
    const ax = new THREE.Vector3(r() * 2 - 1, (r() * 2 - 1) * (o.tilt ?? 2.5), r() * 2 - 1).normalize();
    const u = new THREE.Vector3(1, 0, 0).cross(ax).normalize(), v = ax.clone().cross(u);
    const d = rad[0] + (rad[1] - rad[0]) * Math.pow(r(), 1.3);
    g.userData.o = {u, v, d, ph: r() * TAU, w: (0.05 + 0.1 * r()) * Math.sqrt(40 / d) * (r() < 0.5 ? -1 : 1), s: (o.s0 ?? 0.6) + r() * (o.s1 ?? 1.6), spin: 0.1 + r() * 0.4, band: i % 16, pulse: i % 2 === 0};
    list.push(g);
  }
  return list;
}
function updateSwarm(list, T, k, gain = 1, spread = 1) {
  list.forEach((g) => {
    const o = g.userData.o, a = o.ph + T * o.w, c = Math.cos(a) * o.d * spread, s = Math.sin(a) * o.d * spread;
    g.position.set(o.u.x * c + o.v.x * s, o.u.y * c + o.v.y * s, o.u.z * c + o.v.z * s); g.scale.setScalar(o.s);
    g.rotation.set(T * o.spin + o.ph, T * o.spin * 1.35, o.ph);
    lightCrystal(g, o.pulse ? k : 0.3 * band(T, o.band), gain);
  });
}
// the melody as a line of light: `span` seconds of the pitch of `name`, placed by pos(time, pitch, age, out)
function makeRibbon(n, o = {}) { return new Glow(n + 1, {px: o.px ?? 1.8, world: o.world ?? 0.3, halo: 1.8, haloGain: 0.4, max: o.max ?? 6, parent: o.parent, inPortal: o.inPortal}); }
const RA = [0, 0, 0], RB = [0, 0, 0];
function updateRibbon(gl, name, T, span, pos, cA, cB, gain = 3, tau = 3, glide = 0.2) {
  GLIDE = glide;
  const n = gl.max - 1, dt = span / n;
  let m0 = melody(name, T); pos(T, m0[0], 0, RA);
  gl.dot(n, RA[0], RA[1], RA[2]); gl.col(n, WHITE, gain * 1.6 * m0[1], 2.8);
  for (let i = 0; i < n; i++) {
    const age = (i + 1) * dt, m1 = melody(name, T - age); pos(T - age, m1[0], age, RB);
    gl.seg(i, RA[0], RA[1], RA[2], RB[0], RB[1], RB[2]);
    gl.col(i, lerpC(cA, cB, age / span * 1.4), gain * Math.min(m0[1], m1[1]) * Math.exp(-age / tau), 1 + 0.8 * Math.exp(-age * 3));
    RA[0] = RB[0]; RA[1] = RB[1]; RA[2] = RB[2]; m0 = m1;
  }
  GLIDE = null;
  gl.flush();
}
// the spectrum as rays: 96 bars about a centre (the 16 bands, mirrored, three times round)
function makeSpectrum(parent, o = {}) { return new Glow(96, {parent, px: o.px ?? 2.0, world: o.world ?? 1.0, halo: 1.3, haloGain: 0.3, max: 8, inPortal: o.inPortal}); }
function updateSpectrum(gl, T, r0, len, cA, cB, gain = 1.6) {
  for (let i = 0; i < 96; i++) {
    const m = i % 32, b = m < 16 ? m : 31 - m, a = (i / 96) * TAU + Math.PI / 2, h = band(T, b), r1 = r0 + len * (0.06 + h), c = Math.cos(a), s = Math.sin(a);
    gl.seg(i, c * r0, s * r0, 0, c * r1, s * r1, 0); gl.col(i, lerpC(cA, cB, b / 15), gain * (0.35 + 1.1 * h));
  }
  gl.flush();
}
// rings flying past on the beat: one for every `per` seconds still ahead; zOf(time) is where that moment lies ahead
function updateTunnel(gl, T, per, zOf, far, rad, look) {
  const first = Math.floor(T / per + 1e-6) + 1, count = Math.floor(gl.max / 8);
  for (let j = 0; j < count; j++) {
    const idx = first + j, tk = idx * per, z = zOf(tk), bar = Math.floor(tk / BAR + 1e-6), sides = POLY[bar % 4];
    const fade = sstep(-far, -far * 0.65, z) * sstep(-4, -18, z), L = look(idx, bar), rot = tk * 0.5 + (idx % 2 ? Math.PI / sides : 0);
    for (let q = 0; q < 8; q++) {
      const i = j * 8 + q;
      if (q >= sides) { gl.hide(i); continue; }
      const a = rot + (q / sides) * TAU, b = rot + ((q + 1) / sides) * TAU;
      gl.seg(i, Math.cos(a) * rad, Math.sin(a) * rad, z, Math.cos(b) * rad, Math.sin(b) * rad, z); gl.col(i, L[0], L[1] * fade);
    }
  }
  gl.flush();
}
// a clock: every tick of the score lights the next mark of a dial of 16
function tickDial(dial, T, c, base = 0.18) {
  const ticks = AU.hits.tick, ti = lastIdx(ticks.t, T), te = env("tick", T, 0.22), on = ti >= 0 && T - ticks.t[ti] < 4 ? 1 : 0;
  for (let i = 0; i < 16; i++) { const back = ((ti - i) % 16 + 16) % 16; dial.col(i, c, on * (base + (back < 5 ? te * Math.pow(0.5, back) * 3.2 : 0))); }
  dial.flush(false, true); dial.mesh.quaternion.copy(C.quaternion);
}
// the sun of the drop: a crystal with the tesseract inside, the spectrum as its rays, a ring, the lead as an orbit
function makeSun(o = {}) {
  const g = new THREE.Group(); S.add(g);
  const core = crystal("dodeca", GOLD, ORANGE, {parent: g, world: 0.25, gain: 1.2, base: 0.035, rim: 0.6}); core.scale.setScalar(11);
  const tes = makeTesseract({parent: g, world: 0.12}); tes.scale.setScalar(3.6);
  const spec = makeSpectrum(g, o);
  const ring = Glow.from(circlePts(160, 1), {parent: g, px: 2.4, world: 0.9, halo: 1.8, haloGain: 0.45, max: 9});
  const ring2 = Glow.from(circlePts(160, 1), {parent: g, px: 1.0, world: 0.2, halo: 1.2, haloGain: 0.3});
  const rib = makeRibbon(200, {parent: g, world: 0.8, px: 2.0, max: 8});
  const flare = makeFlare(1, {streak: 1.5, rays: 0.6});
  return {g, core, tes, spec, ring, ring2, rib, flare};
}
// o: {k (kick 0..1), cA, cB (spectrum), cR (ring), r0, len, R (ring radius), gain, lead: [centre pitch], flare, flareC, flareS}
function updateSun(sun, T, o) {
  const k = o.k ?? 0, g = o.gain ?? 1;
  sun.core.rotation.set(T * 0.11, T * 0.17, 0); lightCrystal(sun.core, k, g);
  updateTesseract(sun.tes, tesAngs(T * 0.5), lc(GOLD, WHITE, 0.4 + 0.6 * k), (1.0 + 1.2 * k) * g, (2.2 + 2 * k) * g);
  updateSpectrum(sun.spec, T, o.r0 ?? 17, o.len ?? 40, o.cA, o.cB, 1.15 * g);
  sun.ring.mesh.scale.setScalar(o.R ?? 68); sun.ring.tint(lc(o.cR, WHITE, 0.4 * k), (0.7 + 1.5 * k) * g);
  sun.ring2.mesh.scale.setScalar((o.R ?? 68) * 1.06); sun.ring2.tint(o.cR, 0.6 * g);
  if (o.lead) {
    const R0 = (o.R ?? 68) * 1.22, pc = o.lead;
    updateRibbon(sun.rib, "lead", T, 1.85 * BAR, (tau, p, age, out) => { const a = Math.PI / 2 - (tau / (2 * BAR)) * TAU, r = R0 + (p - pc) * 2.0; out[0] = Math.cos(a) * r; out[1] = Math.sin(a) * r; out[2] = 0; }, WHITE, o.cR, 3.2 * g, 2.2);
    sun.rib.mesh.visible = true;
  } else sun.rib.mesh.visible = false;
  sun.flare.position.copy(sun.g.position);
  setFlare(sun.flare, o.flareC ?? GOLD, o.flare ?? 1, T * 0.07, o.flareS ?? 60);
}
// the sky of the other universe (seen through the portal of groove 2, then the place of the heart)
function heartSky(sky, T, dir) {
  const tt = T - 40 * BAR, p = clamp(tt / (16 * BAR)), hk = tt > 0 ? melody("hook", T)[1] : 0;
  skyTurn(sky.u, T);
  skyColors(sky, hx(0x070209), lc(hx(0x3a0f2c), hx(0x4a1c14), p), lc(hx(0xd0607a), hx(0xe8905a), p), 0.30 + 0.12 * p);
  skyLight(sky, 1, dir, lc(ROSE, GOLD, 0.2 + 0.6 * p), 0.05 + 0.04 * hk + 0.05 * p, 7);
  skyLight(sky, 2, V3b.set(-0.5, 0.6, 0.3), VIO, 0.05, 3);
}
const COLD = new THREE.Color(0.97, 1.0, 1.06), WARM = new THREE.Color(1.05, 0.995, 0.93), HOT = new THREE.Color(1.07, 1.0, 0.9);

// ---- groove 2 (bars 32-40): out of the tunnel; a great portal ahead shows the other universe, and we fly into it ----
MODES.groove2 = {
  build() {
    O.sky = makeSky(12);
    O.skyB = makeSky(21); O.skyB.mesh.visible = false;
    O.stars = makeStars(800, [22, 240], 520, 17, {tints: [WHITE, ICE, CYAN, VIO]});
    O.field = makeField(40, [13, 58], 420, 6, [CYAN, VIO, BLUE, ICE], {gain: 1.4, s0: 0.7, s1: 2.2, kinds: 5});
    O.portal = makePortal(62, O.skyB);
    O.side = [[-25, 9, 0.36], [27, -12, 0.62], [-17, -15, 0.84]].map((q) => { const g = makePortal(7, O.skyB); g.userData.q = q; return g; });
    O.flareB = makeFlare(1, {streak: 1.0, rays: 0.3, inPortal: true});
    O.glints = new Glow(60, {px: 1.6, halo: 1.6, haloGain: 0.5});
  },
  frame(T, t) {
    const L = 8 * BAR, p = clamp(t / L), k = kick(T), clap = env("clap", T, 0.14), lv = level(T), TOT = 560;
    const distAt = (u) => 24 * u * L + (TOT - 24 * L) * Math.pow(u, 1.5), dist = distAt(p), D = TOT - dist + 3;
    const roll = mix(T * 0.06 + 0.1 * Math.sin(T * 0.23), TAU, ease(p)), calm = 1 - ease(p);
    setCam(Math.cos(T * 0.5) * 1.5 * calm, Math.sin(T * 0.37) * 1.3 * calm, 0, 0, 0, -80, roll, 64 - 4 * ease(p));
    skyTurn(O.sky.u, T, 2);
    skyColors(O.sky, hx(0x02010c), hx(0x150a48), hx(0x2a7fd0), 0.34 + 0.12 * lv);
    skyLight(O.sky, 1, V3.set(0, 0, -1), lerpC(CYAN, MAG, clap * 0.6), 0.07 + 0.1 * clap, 8);
    skyLight(O.sky, 2, V3.set(0.7, 0.4, -0.5), VIO, 0.04, 3);
    heartSky(O.skyB, T, V3.set(0, 0, -1));
    updateStars(O.stars, T, dist * 1.2, 1.2 + 2.5 * p, 0, 1);
    updateField(O.field, T, dist * 2.2, 0, 1, 0.9, 12);
    const eighth = Math.floor(T / (BEAT / 2) + 1e-6), ee = Math.exp(-(T - eighth * BEAT / 2) / 0.12);
    O.portal.position.set(0, 0, -D);
    lightPortal(O.portal, lc(ROSE, GOLD, 0.45), 1.8 * (1 + 1.3 * k), WHITE, 0.7, 1 + 0.35 * clap);
    lightDial(O.portal, lc(GOLD, WHITE, 0.3), 0.5, eighth, ee);
    O.side.forEach((g, i) => {
      const q = g.userData.q, z = -(distAt(q[2]) - dist);
      g.visible = z < -1.5; g.position.set(q[0], q[1], z); g.rotation.set(0.3 * Math.sin(T * 0.3 + i), -q[0] * 0.02 + 0.3 * Math.sin(T * 0.21 + i * 2), T * 0.1);
      const far = sstep(-420, -220, z);
      lightPortal(g, lc(ROSE, GOLD, 0.3 + 0.3 * i), 1.6 * far * (1 + 1.3 * k), WHITE, 0.6 * far, far * (1 + 0.35 * clap)); lightDial(g, GOLD, 0.4 * far, eighth, ee * far);
    });
    O.flareB.position.set(0, 0, -D - 95);
    setFlare(O.flareB, lc(ROSE, GOLD, 0.5), 0.5, T * 0.04, 30);
    updateGlints(O.glints, "call", T, {life: 3.5, c: GOLD, size: 1.6, gain: 4, rise: 0.04, place: (j, pitch) => { const a = hash1(j, 1) * TAU, z = -Math.max(D, 70), rr = (70 + 12 * hash1(j, 2)) * Math.min(1, -z / 300 + 0.25); return [Math.cos(a) * rr, Math.sin(a) * rr * 0.7 + (pitch - 50) * 0.5, z]; }});      // the choir's groove phrase, two octaves under v6
    const end = sstep(7.4 * BAR, 8 * BAR, t);
    finish(T, {exp: 1.02, bloom: 0.7, flash: 1.0 * Math.exp(-t / 0.3) + 0.5 * Math.pow(end, 4), flashCol: lc(ICE, GOLD, end), lift: hx(0x02020a), gain: lc(COLD, WARM, ease(p)), ca: 0.9});
  },
};

// ---- heart (bars 40-56): the other universe. The hook, sung slowly, is a line of light about a great crystal;
//      then the ostinato returns, great rings wake around it and the camera pulls far back ----
MODES.heart = {
  build() {
    O.sky = makeSky(21);
    O.shell = makeShell(800, 140, 1100, 41);
    O.rings = makeRings();
    O.core = crystal("ico", GOLD, ROSE, {world: 0.2, gain: 1.0, base: 0.045, rim: 0.6}); O.core.scale.setScalar(14);
    O.tes = makeTesseract({world: 0.1}); O.tes.scale.setScalar(3.4);
    O.flare = makeFlare(1, {streak: 1.0, rays: 0.3});
    O.rib = makeRibbon(260, {world: 0.35, px: 1.9});
    O.swarm = makeSwarm(34, [24, 115], 9, [ROSE, AMBER, GOLD, VIO], {s0: 0.5, s1: 1.7});
    O.shocks = makeShocks(3, 128);
    O.glints = new Glow(60, {px: 1.6, halo: 1.6, haloGain: 0.5});
    O.glints2 = new Glow(80, {px: 1.6, halo: 1.6, haloGain: 0.5});
    const marks = []; for (let i = 0; i < 16; i++) { const a = (i / 16) * TAU; marks.push(Math.sin(a) * 19, Math.cos(a) * 19, 0, Math.sin(a) * (i % 4 ? 20.2 : 21.6), Math.cos(a) * (i % 4 ? 20.2 : 21.6), 0); }
    O.dial = Glow.from(marks, {px: 1.3, world: 0.14});
  },
  frame(T, t) {
    const tt = T - 40 * BAR, H8 = 8 * BAR, p = clamp(tt / (2 * H8)), u = clamp((tt - H8) / H8), us = u * u * (3 - 2 * u);
    const hk = melody("hook", T)[1], boom = env("boom", T, 1.3), taiko = env("taiko", T, 0.5), frame = env("frame", T, 0.22);
    const r = tt < H8 ? mix(95, 50, ease(tt / H8)) : 50 + 420 * us, th = 0.05 * tt + 0.5 * us, y = 3 + r * 0.1 + 110 * us;
    const off = r * 0.16 * sstep(0, 2.5 * BAR, tt) * (1 - us);
    setCam(Math.sin(th) * r, y, Math.cos(th) * r, Math.cos(th) * off, 1 - 4 * us, -Math.sin(th) * off, 0.04 * Math.sin(T * 0.11), 52 + 4 * us);
    heartSky(O.sky, T, V3.copy(C.position).negate());
    if (taiko > 0.01) { const ti = lastIdx(AU.hits.taiko.t, T); skyLight(O.sky, 2, V3b.set(Math.cos(ti * 2.4), 0.3 + 0.4 * Math.sin(ti * 1.7), Math.sin(ti * 2.4)), lc(AMBER, WHITE, 0.3), 0.3 * taiko, 4); }
    O.shell.tint(WHITE, 1);
    const ost = ostEnv(T, 0.1);
    updateRings(O.rings, T, (q) => lc(ROSE, AMBER, 0.2 + 0.12 * q + 0.25 * u), (q) => sstep(q * 0.1 - 0.12, q * 0.1 + 0.25, (tt - 7 * BAR) / (9 * BAR)) * (0.4 + 0.25 * u) * (1 + 0.9 * u * ostEnv(T - q * 0.03, 0.12)) * (1 + 0.8 * taiko));
    O.core.rotation.set(T * 0.05, T * 0.08, 0); lightCrystal(O.core, clamp(0.3 * hk + 0.5 * boom), 1);
    updateTesseract(O.tes, tesAngs(T * 0.3 + 1), lc(GOLD, WHITE, 0.3 + 0.5 * hk), 1.2 + 1.4 * hk + boom, 2.4 + 4 * frame + 1.5 * ost * u);
    O.flare.position.set(0, 0, 0);
    setFlare(O.flare, lc(ROSE, GOLD, 0.5 + 0.5 * p), 0.3 + 0.4 * hk + 0.7 * boom + 0.4 * taiko, T * 0.04, (22 + 6 * hk) * (1 + 1.6 * us));
    const wide = 1 + 2.2 * us;
    updateRibbon(O.rib, "hook", T, 9, (tau, pitch, age, out) => { const a = tau * 0.85, rr = (21 + age * 2.4) * wide; out[0] = Math.cos(a) * rr; out[1] = (pitch - 62) * 1.3 * wide; out[2] = Math.sin(a) * rr; }, lc(GOLD, WHITE, 0.5), ROSE, 3.2, 3.5);
    O.rib.mat.uniforms.uWorld.value = 0.35 * wide;
    updateSwarm(O.swarm, T, 0.35 * hk + 0.5 * taiko, 0.9);
    updateShocks(O.shocks, "boom", T, lc(ROSE, GOLD, p), {at: ORIGIN, r0: 15, r1: 260, life: 5.5, gain: 2.2, face: true});
    updateGlints(O.glints, "swell", T, {life: 4, rise: 0.4, c: ROSE, size: 1.5 * wide, gain: 4, place: (j) => { const a = hash1(j, 1) * TAU, rr = (30 + 26 * hash1(j, 2)) * wide; return [Math.cos(a) * rr, (hash1(j, 3) - 0.5) * 44 * wide, Math.sin(a) * rr]; }});
    updateGlints(O.glints2, "call", T, {n: 16, life: 3, rise: 0.07, c: GOLD, size: 2.6 * wide, gain: 4.5, place: (j, pitch) => { const a = j * 0.72; return [Math.cos(a) * 70, (pitch - 64) * 2.4, Math.sin(a) * 70]; }});   // violas, an octave under v6's violins
    tickDial(O.dial, T, GOLD, 0.15);
    finish(T, {exp: 0.95 + 0.05 * p, bloom: 0.7, flash: 0.6 * Math.exp(-tt / 0.5) + 0.2 * env("boom", T, 0.35) * sstep(1, 2, tt), flashCol: lc(ROSE, GOLD, 0.5), lift: hx(0x060204), gain: WARM, vig: 0.7, ca: 0.5});
  },
};

// ---- build (bars 56-64): the corridor again, hot and faster and faster towards a white star; then a breath of dark ----
MODES.build = {
  build() {
    O.sky = makeSky(25);
    O.stars = makeStars(900, [20, 260], 600, 19, {tints: [WHITE, GOLD, AMBER, ROSE]});
    O.lat = makeLattice(14, 22, 12);
    O.field = makeField(26, [17, 46], 320, 8, [AMBER, GOLD, ROSE, ORANGE], {gain: 1.4, s0: 0.6, s1: 1.4, kinds: 5});
    O.flare = makeFlare(1, {streak: 1.6, rays: 0.7});
    O.tes = makeTesseract({world: 0.4}); O.tes.scale.setScalar(9);
  },
  frame(T, t) {
    const tt = T - 56 * BAR, L = 8 * BAR, p = clamp(tt / L), k = kick(T), taiko = env("taiko", T, 0.3), tom = env("tom", T, 0.2), roll = env("roll", T, 0.09);
    const gap = sstep(7.6 * BAR, 7.68 * BAR, tt), live = 1 - gap, dist = 40 * tt + 70 * tt * tt / L, hot = p * p;
    setCam(1.4 * Math.sin(T * 0.4) * live, 1.2 * Math.cos(T * 0.31) * live, 0, 0, 0, -100, 0.02 * tt * tt, 58 + 12 * hot);
    skyTurn(O.sky.u, T, 2);
    skyColors(O.sky, hx(0x080203), lc(hx(0x3a1008), hx(0x6a2a08), p), lc(hx(0xff7a30), hx(0xffd9a0), hot), (0.36 + 0.5 * hot) * (0.04 + 0.96 * live));
    skyLight(O.sky, 1, V3.set(0, 0, -1), lc(AMBER, WHITE, hot), (0.1 + 0.5 * hot + 0.12 * roll * p) * live, 7 - 3 * hot);
    const ti = lastIdx(AU.hits.tom.t, T);
    skyLight(O.sky, 2, V3.set(Math.cos(ti * 2.4) * 0.8, Math.sin(ti * 1.7) * 0.6, -0.6), lc(ORANGE, GOLD, 0.5), 0.3 * tom * live, 5);
    updateStars(O.stars, T, dist * 0.6, 1 + 9 * hot, 0, live);
    updateLattice(O.lat, T, dist, 0, lc(ORANGE, WHITE, 0.15 + 0.6 * hot), (i, ahead) => live * (0.2 + 0.25 * p + 1.6 * ostEnv(tt - ahead / 500) + (1.2 + p) * k * Math.exp(-ahead / 140) + 1.5 * taiko * Math.exp(-ahead / 80) + 0.8 * roll * p), 0.5);
    updateField(O.field, T, dist, 0, 1, live, 12);
    O.flare.position.set(0, 0, -420); O.tes.position.set(0, 0, -420);
    updateTesseract(O.tes, tesAngs(T * 0.6), lc(GOLD, WHITE, hot), (1.4 + 1.5 * k) * live, (3 + 3 * k) * live);
    setFlare(O.flare, lc(AMBER, WHITE, 0.3 + 0.7 * hot), (0.6 + 1.8 * hot + 0.4 * k) * live + 0.6 * gap, T * 0.12, (50 + 170 * hot) * live + 44 * gap);
    finish(T, {exp: 1.0 + 0.45 * hot * live, bloom: 0.7 + 0.25 * hot, flash: 0.7 * Math.exp(-tt / 0.3) + 0.9 * Math.pow(p, 7) * live, flashCol: lc(AMBER, WHITE, 0.6), lift: hx(0x050203), gain: lc(WARM, HOT, p), vig: 0.6, ca: 0.6 + 1.2 * hot});
  },
};

// ---- drop 1 (bars 64-72): the sun. The spectrum is its rays, the lead is its orbit, the kick sends rings down the flight ----
function dropSky(sky, T, hotter = 0) {
  const lv = level(T), clap = env("clap", T, 0.16);
  skyColors(sky, hx(0x09020e), lc(hx(0x4a0a3a), hx(0x5a1a0c), hotter), lc(hx(0xff6a3a), hx(0xffc070), hotter), 0.27 + 0.13 * lv + 0.08 * hotter);
  return clap;
}
MODES.drop1 = {
  build() {
    O.sky = makeSky(30);
    O.stars = makeStars(900, [24, 280], 620, 23, {tints: [WHITE, GOLD, ROSE, MAG]});
    O.tun = new Glow(14 * 8, {px: 1.5, world: 0.1, halo: 1.6, haloGain: 0.35, max: 5});
    O.field = makeField(34, [19, 62], 300, 14, [MAG, ORANGE, GOLD, VIO], {gain: 1.5, s0: 0.7, s1: 1.8, kinds: 5});
    O.sun = makeSun();
    O.shocks = makeShocks(3, 128);
  },
  frame(T, t) {
    const v = 92, k = kick(T), snare = env("snare", T, 0.2), taiko = env("taiko", T, 0.4), DS = 265;
    const roll = 0.22 * Math.sin(T * 0.21) + 0.05 * t;
    setCam(Math.cos(T * 0.5) * 2.6, Math.sin(T * 0.37) * 2.2, 0, Math.cos(T * 0.31) * 14, Math.sin(T * 0.26) * 9, -DS, roll, 64);
    skyTurn(O.sky.u, T, 2.5);
    const clap = dropSky(O.sky, T, 0);
    skyLight(O.sky, 1, V3.set(0, 0, -1), lc(ORANGE, GOLD, 0.4), 0.09 + 0.14 * taiko, 5);
    skyLight(O.sky, 2, V3.set(Math.cos(T * 0.2) * 0.8, 0.5, -0.4), MAG, 0.05 + 0.14 * clap, 4);
    updateStars(O.stars, T, v * T * 0.7, 3.2, 0, 1);
    updateTunnel(O.tun, T, BEAT, (tk) => -(tk - T) * v - 3, 520, 15, (idx, bar) => [lerpC(bar % 2 ? MAG : ORANGE, WHITE, 0.55 * k), 1.1 + 2.8 * k]);
    updateField(O.field, T, v * T * 0.8, 0, 1, 0.95, 12);
    O.sun.g.position.set(0, 0, -DS); O.sun.g.quaternion.copy(C.quaternion);
    updateSun(O.sun, T, {k, cA: lc(GOLD, ORANGE, 0.45), cB: MAG, cR: lc(ORANGE, GOLD, 0.5), r0: 17, len: 42, R: 70, lead: 85, flare: 0.24 + 0.26 * k + 0.2 * taiko, flareC: lc(ORANGE, GOLD, 0.6), flareS: 46});
    updateShocks(O.shocks, "taiko", T, lc(GOLD, WHITE, 0.4), {at: O.sun.g.position, r0: 20, r1: 300, life: 2.6, gain: 3, face: true, only: (tj) => Math.abs(tj / (4 * BAR) - Math.round(tj / (4 * BAR))) < 0.01});
    finish(T, {exp: 1.0, bloom: 0.7, flash: 1.3 * Math.exp(-t / 0.28), flashCol: lc(GOLD, WHITE, 0.6), lift: hx(0x060208), gain: WARM, sat: 1.12, ca: 1.0, vig: 0.5});
  },
};

// ---- drop 2 (bars 72-80): around the sun; five portals show the cold universe we came from ----
MODES.drop2 = {
  build() {
    O.sky = makeSky(30);
    O.skyB = makeSky(3); O.skyB.mesh.visible = false;
    O.shell = makeShell(700, 180, 1000, 43, {tints: [WHITE, GOLD, ROSE, MAG]});
    O.shellB = makeShell(500, 200, 900, 47, {tints: [WHITE, ICE, CYAN], inPortal: true});
    O.sun = makeSun();
    O.portals = [0, 1, 2, 3, 4].map((i) => {
      const g = makePortal(26, O.skyB), a = (i / 5) * TAU; g.userData.a = a;
      const tes = makeTesseract({world: 0.3, inPortal: true}); tes.position.set(Math.sin(a) * 215, 0, Math.cos(a) * 215); tes.scale.setScalar(13); g.userData.tes = tes;
      return g;
    });
    O.swarm = makeSwarm(40, [84, 190], 15, [MAG, ORANGE, GOLD, VIO], {s0: 1.0, s1: 3.2, world: 0.1});
    O.shocks = makeShocks(3, 128);
  },
  frame(T, t) {
    const k = kick(T), taiko = env("taiko", T, 0.4), p = clamp(t / (8 * BAR));
    const th = 0.4 + t * 0.2, r = 245 - 30 * Math.sin(t * 0.33), y = 60 * Math.sin(t * 0.24 + 0.6);
    setCam(Math.sin(th) * r, y, Math.cos(th) * r, 0, 0, 0, 0.14 * Math.sin(T * 0.19), 62);
    skyTurn(O.sky.u, T, 2.5); skyTurn(O.skyB.u, T);
    const clap = dropSky(O.sky, T, 0.3 * p);
    skyLight(O.sky, 1, V3.copy(C.position).negate(), lc(ORANGE, GOLD, 0.5), 0.09 + 0.14 * taiko, 5);
    skyLight(O.sky, 2, V3b.set(Math.cos(T * 0.2) * 0.8, 0.5, Math.sin(T * 0.2)), MAG, 0.05 + 0.14 * clap, 4);
    skyColors(O.skyB, hx(0x00030a), hx(0x04264a), hx(0x28b4dc), 0.5);
    skyLight(O.skyB, 1, V3.copy(C.position).negate(), CYAN, 0.05, 6); skyLight(O.skyB, 2, V3b.set(0, 1, 0), BLUE, 0.05, 3);
    O.shell.tint(WHITE, 1); O.shellB.tint(WHITE, 1.3);
    O.sun.g.rotation.set(0, th * 0.75, T * 0.03);
    updateSun(O.sun, T, {k, cA: lc(GOLD, ORANGE, 0.45), cB: MAG, cR: lc(ORANGE, GOLD, 0.6), r0: 17, len: 44, R: 60, lead: 85, flare: 0.2 + 0.22 * k + 0.2 * taiko, flareC: lc(ORANGE, GOLD, 0.6), flareS: 44, gain: 0.85});
    const eighth = Math.floor(T / (BEAT / 2) + 1e-6), ee = Math.exp(-(T - eighth * BEAT / 2) / 0.12);
    O.portals.forEach((g, i) => {
      const a = g.userData.a + T * 0.05, R = 108, on = Math.floor(T / BEAT + 1e-6) % 5 === i ? k : 0.25 * k;
      g.position.set(Math.sin(a) * R, 26 * Math.sin(T * 0.13 + i * 1.9), Math.cos(a) * R); g.rotation.set(0, a, 0);
      lightPortal(g, lc(CYAN, WHITE, 0.5 * on), 0.9 + 1.8 * on, ICE, 0.5, 1 + 0.3 * clap); lightDial(g, ICE, 0.45, eighth + i * 9, ee);
      const tes = g.userData.tes; tes.position.set(Math.sin(a) * 235, g.position.y, Math.cos(a) * 235);
      updateTesseract(tes, tesAngs(T * 0.5 + i), lc(CYAN, ICE, 0.5), 1.6 + 1.6 * on, 3);
    });
    updateSwarm(O.swarm, T, k, 0.95);
    updateShocks(O.shocks, "taiko", T, lc(GOLD, WHITE, 0.4), {at: ORIGIN, r0: 20, r1: 330, life: 2.6, gain: 3, face: true, only: (tj) => Math.abs(tj / (4 * BAR) - Math.round(tj / (4 * BAR))) < 0.01});
    finish(T, {exp: 1.0, bloom: 0.7, flash: 1.0 * Math.exp(-t / 0.28), flashCol: lc(MAG, WHITE, 0.6), lift: hx(0x060208), gain: WARM, sat: 1.12, ca: 0.9, vig: 0.5});
  },
};

// ---- climax (bars 80-88) and afterglow (bars 88-96): the sun inside the great rings, and all of it seen from far away ----
function megaBuild(seed) {
  O.sky = makeSky(seed);
  O.shell = makeShell(900, 320, 1500, 51, {tints: [WHITE, WHITE, GOLD, ROSE]});
  O.rings = makeRings();
  O.sun = makeSun();
  O.swarm = makeSwarm(44, [44, 270], 21, [GOLD, MAG, AMBER, ROSE], {s0: 1.2, s1: 4.5, world: 0.14, tilt: 0.5});
  O.shocks = makeShocks(3, 160);
  O.glints = new Glow(80, {px: 1.8, halo: 1.6, haloGain: 0.5});
  O.rib = makeRibbon(220, {world: 0.9, px: 2.0, max: 8});
}
const megaCam = (tc) => { const p = clamp(tc / (8 * BAR)), q = clamp(tc / (8 * BAR) - 1), r = 150 + 520 * p * p * (3 - 2 * p) - 400 * q * q * (3 - 2 * q); return {r, th: 0.9 + 0.11 * Math.min(tc, 8 * BAR) + 0.05 * Math.max(0, tc - 8 * BAR), y: 14 + r * 0.3}; };
MODES.climax = {
  build() { megaBuild(33); },
  frame(T, t) {
    const tc = T - 80 * BAR, p = clamp(tc / (8 * BAR)), k = kick(T), taiko = env("taiko", T, 0.4), crash = env("crash", T, 0.5), cam = megaCam(tc);
    setCam(Math.sin(cam.th) * cam.r, cam.y, Math.cos(cam.th) * cam.r, 0, -cam.r * 0.04, 0, 0.1 * Math.sin(T * 0.17), 58);
    skyTurn(O.sky.u, T, 2);
    const clap = env("clap", T, 0.16);
    skyColors(O.sky, hx(0x0b0410), hx(0x5e0e26), hx(0xffb060), 0.27 + 0.12 * level(T) + 0.05 * p);
    skyLight(O.sky, 1, V3.copy(C.position).negate(), lc(GOLD, WHITE, 0.5), 0.13 + 0.14 * taiko + 0.08 * crash, 4.5);
    skyLight(O.sky, 2, V3b.set(Math.cos(T * 0.2), 0.6, Math.sin(T * 0.2)), ROSE, 0.05 + 0.12 * clap, 4);
    O.shell.tint(WHITE, 1.1);
    updateRings(O.rings, T, (q) => lc(q % 2 ? GOLD : WHITE, AMBER, 0.25), (q) => (0.5 + 0.1 * q) * (1 + 1.5 * (Math.floor(T / BEAT + 1e-6) % 5 === q ? k : 0.45 * k)) * (1 + 0.5 * taiko), 2.2);
    O.sun.g.rotation.set(-1.15, 0, T * 0.06);
    updateSun(O.sun, T, {k, cA: WHITE, cB: ORANGE, cR: GOLD, r0: 17, len: 52, R: 82, lead: 90, flare: 0.5 + 0.4 * k + 0.35 * taiko, flareC: lc(GOLD, WHITE, 0.4), flareS: 50 + cam.r * 0.1, gain: 1.1});
    updateSwarm(O.swarm, T, k, 1);
    updateShocks(O.shocks, "taiko", T, lc(GOLD, WHITE, 0.5), {at: ORIGIN, r0: 20, r1: 520, life: 3.2, gain: 3.2, face: true, only: (tj) => Math.abs(tj / (2 * BAR) - Math.round(tj / (2 * BAR))) < 0.01});
    updateGlints(O.glints, "call", T, {n: 16, life: 2.2, rise: 0.04, c: GOLD, size: 5 + cam.r * 0.012, gain: 5, place: (j, pitch) => { const a = j * 0.55; return [Math.cos(a) * 118, (pitch - 56) * 3.4 + 20, Math.sin(a) * 118]; }});   // violas, an octave under v6
    O.rib.mesh.visible = false;
    finish(T, {exp: 1.03, bloom: 0.75, flash: 1.5 * Math.exp(-tc / 0.3) + 0.3 * crash * sstep(1, 2, tc), flashCol: lc(GOLD, WHITE, 0.7), lift: hx(0x070402), gain: HOT, sat: 1.1, ca: 0.9, vig: 0.5});
  },
};
MODES.afterglow = {
  build() { megaBuild(33); },
  frame(T, t) {
    const tc = T - 80 * BAR, ta = T - 88 * BAR, p = clamp(ta / (8 * BAR)), k = kick(T) * (1 - 0.75 * p), taiko = env("taiko", T, 0.6), boom = env("boom", T, 1.2), cam = megaCam(tc), hk = melody("hook", T)[1];
    setCam(Math.sin(cam.th) * cam.r, cam.y, Math.cos(cam.th) * cam.r, 0, -cam.r * 0.04, 0, 0.1 * Math.sin(T * 0.17), 58 - 4 * p);
    skyTurn(O.sky.u, T, 2 - p);
    skyColors(O.sky, hx(0x070308), lc(hx(0x5e0e26), hx(0x1c1040), p), lc(hx(0xffb060), hx(0x8a66d8), p), 0.32 - 0.06 * p);
    skyLight(O.sky, 1, V3.copy(C.position).negate(), lc(GOLD, ROSE, p), 0.12 - 0.05 * p + 0.12 * taiko + 0.04 * hk, 5);
    skyLight(O.sky, 2, V3b.set(Math.cos(T * 0.2), 0.6, Math.sin(T * 0.2)), VIO, 0.06, 4);
    O.shell.tint(WHITE, 1.1);
    updateRings(O.rings, T, (q) => lc(lc(GOLD, AMBER, 0.25), q % 2 ? VIO : ROSE, p), (q) => (0.62 - 0.3 * p) * (1 + 1.2 * k) * (1 + 0.5 * taiko), 2.2 - 1.2 * p);
    O.sun.g.rotation.set(-1.15, 0, T * 0.06);
    updateSun(O.sun, T, {k, cA: lc(WHITE, ROSE, p), cB: lc(ORANGE, VIO, p), cR: lc(GOLD, ROSE, p), r0: 17, len: 52 - 20 * p, R: 82, flare: 0.45 - 0.1 * p + 0.35 * k + 0.3 * taiko + 0.25 * hk, flareC: lc(GOLD, ROSE, 0.6 * p), flareS: 50 + cam.r * 0.1, gain: 1.1 - 0.4 * p});
    updateSwarm(O.swarm, T, clamp(k + 0.3 * hk), 1 - 0.3 * p);
    updateShocks(O.shocks, "taiko", T, lc(GOLD, ROSE, p), {at: ORIGIN, r0: 20, r1: 520, life: 5, gain: 2.6, face: true});
    updateRibbon(O.rib, "hook", T, 9, (tau, pitch, age, out) => { const a = tau * 0.6, rr = 96 + age * 7; out[0] = Math.cos(a) * rr; out[1] = (pitch - 62) * 4.2 + 22; out[2] = Math.sin(a) * rr; }, lc(GOLD, WHITE, 0.5), ROSE, 3.4, 3.5);
    O.rib.mesh.visible = true;
    updateGlints(O.glints, "swell", T, {n: 16, life: 4, rise: 0.4, c: ROSE, size: 4, gain: 4, place: (j) => { const a = hash1(j, 1) * TAU, rr = 110 + 60 * hash1(j, 2); return [Math.cos(a) * rr, (hash1(j, 3) - 0.3) * 90, Math.sin(a) * rr]; }});
    finish(T, {exp: 1.03 - 0.03 * p, bloom: 0.75, flash: 0.5 * Math.exp(-ta / 0.6), flashCol: lc(GOLD, WHITE, 0.5), lift: lc(hx(0x070402), hx(0x040308), p), gain: lc(HOT, ONE, p), sat: 1.1 - 0.06 * p, ca: 0.7, vig: 0.55 + 0.1 * p});
  },
};

// ---- coda (bars 96-104 and the last chord's tail): the one light again, far in a large dark, now warm; the end card ----
const TAIL = 4.6;
MODES.coda = {
  build() {
    O.sky = makeSky(3);
    O.stars = makeStars(900, [14, 260], 620, 11);
    O.dust = makeStars(160, [3, 40], 160, 29, {px: 3.2, tints: [ICE, GOLD, WHITE]});
    O.tes = makeTesseract({world: 0.05}); O.tes.position.set(0, 0, -150); O.tes.scale.setScalar(6.5);
    O.flare = makeFlare(1, {streak: 1.0, rays: 0.3}); O.flare.position.copy(O.tes.position);
    O.shocks = makeShocks(3);
    O.glints = new Glow(80, {px: 1.6, halo: 1.6, haloGain: 0.5});
    const marks = []; for (let i = 0; i < 16; i++) { const a = (i / 16) * TAU; marks.push(Math.sin(a) * 15, Math.cos(a) * 15, 0, Math.sin(a) * (i % 4 ? 16.2 : 17.4), Math.cos(a) * (i % 4 ? 16.2 : 17.4), 0); }
    O.dial = Glow.from(marks, {px: 1.3, world: 0.12}); O.dial.mesh.position.copy(O.tes.position);
  },
  frame(T, t) {
    const L = 8 * BAR, END = L + TAIL, p = clamp(t / L), boom = env("boom", T, 1.4), taiko = env("taiko", T, 0.8), hk = noteAmp("hook", T, 0.3, 2.5);
    const major = sstep(3.6 * BAR, 6.5 * BAR, t), card = sstep(2.9 * BAR, 4.3 * BAR, t), out = 1 - sstep(END - 2.6, END - 0.4, t);
    const cz = -62 + 70 * ease(t / END) , drop = 0.3 * (cz + 150) * ease(clamp(t / (4.3 * BAR)));           // the light sinks under the words
    setCam(Math.sin(T * 0.11) * 2.4, 1.0 + Math.cos(T * 0.09) * 1.2, cz, 0, drop, -150, 0.03 * Math.sin(T * 0.13), 50);
    skyTurn(O.sky.u, T);
    skyColors(O.sky, hx(0x010207), lc(hx(0x051a33), hx(0x1a1430), major), lc(hx(0x3a80a0), hx(0xd08a5a), major), 0.5 - 0.2 * card);
    skyLight(O.sky, 1, V3.set(0, -0.3, -1), lc(ICE, GOLD, 0.3 + 0.7 * major), 0.06 + 0.16 * major + 0.1 * boom + 0.05 * hk, 9);
    skyLight(O.sky, 2, V3.set(-0.6, 0.5, -0.4), BLUE, 0.035, 3);
    updateStars(O.stars, T, -4 * t, 0.0, cz, 1);
    updateStars(O.dust, T, -2 * t, 0.0, cz, 0.12, 4);
    const warm = lc(ICE, GOLD, 0.25 + 0.75 * major);
    updateTesseract(O.tes, tesAngs(T * 0.35 + 2), lc(warm, WHITE, boom), 1.2 + 2.0 * boom + 0.6 * hk + 0.5 * major, 2.4 + 3 * boom);
    setFlare(O.flare, warm, 0.7 + 1.4 * boom + 0.5 * hk + 0.6 * major + 0.5 * taiko, T * 0.05, 28 + 10 * boom + 14 * major);
    updateShocks(O.shocks, "boom", T, warm, {at: O.tes.position, r0: 6, r1: 170, life: 6, gain: 2.2, face: true});
    tickDial(O.dial, T, warm);
    const bt = AU.notes.call.t;
    updateGlints(O.glints, "call", T, {n: 16, life: 4.5, rise: 0.08, c: GOLD, size: 2.0, gain: 5, place: (j) => { const s = (bt[j] / S16) % 32, side = j % 2 ? 1 : -1; return [side * (34 + 3.2 * s) , -52 + 3.4 * s + 10 * hash1(j, 2), -150 + 30 * (hash1(j, 3) - 0.5)]; }});
    finish(T, {exp: 1.0 - 0.12 * card, bloom: 0.7, fade: out, flash: 0.6 * Math.exp(-t / 0.6), flashCol: lc(ROSE, WHITE, 0.5), lift: lc(hx(0x020409), hx(0x050304), major), gain: lc(COLD, WARM, major), vig: 0.7});
    const a = card * out;
    endEl.style.opacity = a.toFixed(3); endEl.style.display = a > 0.002 ? "block" : "none";
  },
};

// ====================================================================================================
function makeText() {
  const css = document.createElement("style");
  css.textContent = `
    .ps-card{position:absolute;left:0;top:0;width:100vw;height:100vh;display:none;pointer-events:none;color:#f4f1ea;text-align:center;font-family:var(--vidgen-font-heading),Inter,sans-serif}
    .ps-title{position:absolute;left:0;right:0;top:22.5vh;font-weight:400;font-size:4.3vw;letter-spacing:.42em;padding-left:.42em;white-space:nowrap;text-shadow:0 0 1.2vw rgba(140,210,255,.55),0 0 .25vw rgba(255,255,255,.7)}
    .ps-rule{position:absolute;left:44vw;width:12vw;top:34.4vh;height:1px;background:linear-gradient(90deg,transparent,#bfe6ff,transparent);opacity:.85}
    .ps-made{position:absolute;left:0;right:0;top:66.4vh;font-size:1.2vw;letter-spacing:.5em;padding-left:.5em;text-transform:uppercase;color:#a9c4d8;white-space:nowrap}
    .ps-url{position:absolute;left:0;right:0;top:70.6vh;font-family:var(--vidgen-font-mono),monospace;font-size:1.62vw;letter-spacing:.02em;color:#e9f4ff;white-space:nowrap;text-shadow:0 0 .8vw rgba(120,200,255,.45)}
    .ps-end .ps-title{top:27vh;font-size:2.5vw;color:#fff3df;text-shadow:0 0 1.2vw rgba(255,200,120,.5),0 0 .25vw rgba(255,255,255,.6)}
    .ps-end .ps-rule{top:35.6vh;background:linear-gradient(90deg,transparent,#ffdca8,transparent)}
    .ps-end .ps-made{top:39.4vh;color:#e2d3bf}
    .ps-end .ps-url{top:44.4vh;font-size:1.9vw;color:#fff6e8;text-shadow:0 0 .8vw rgba(255,190,110,.45)}
    .ps-line{position:absolute;left:0;right:0;font-size:1.72vw;letter-spacing:.16em;padding-left:.16em;white-space:nowrap;color:#fbf3e6;text-shadow:0 0 .6vw rgba(0,0,0,.8)}
    .ps-thanks{position:absolute;left:0;right:0;top:62.5vh;font-size:1.2vw;letter-spacing:.5em;padding-left:.5em;text-transform:uppercase;color:#eadcc8;white-space:nowrap;text-shadow:0 0 .6vw rgba(0,0,0,.8)}`;
  document.head.append(css);
  const el = (cls, text, parent) => { const d = document.createElement("div"); d.className = cls; if (text) d.textContent = text; parent.append(d); return d; };
  titleEl = el("ps-card", "", document.body); titleEl.dataset.vidgenId = "title-card"; titleEl.dataset.vidgenLint = "off";
  el("ps-title", "PARALLEL SPACE", titleEl); el("ps-rule", "", titleEl); el("ps-made", "made with", titleEl);
  el("ps-url", "https://github.com/joaopauloschuler/schu-video-generator", titleEl);
  endEl = el("ps-card ps-end", "", document.body); endEl.dataset.vidgenId = "end-card"; endEl.dataset.vidgenLint = "off";
  el("ps-title", "PARALLEL SPACE", endEl); el("ps-rule", "", endEl); el("ps-made", "made with", endEl);
  el("ps-url", "https://github.com/joaopauloschuler/schu-video-generator", endEl);
  el("ps-line", "is open source. Give it a star on GitHub.", endEl).style.top = "52vh";
  el("ps-thanks", "Thank you for watching!", endEl);
}

export async function load(ctx) {
  mode = ctx.data.mode; t0 = ctx.data.t0; W = ctx.width; H = ctx.height;
  AU = loadAudio(await (await fetch(new URL("./ps_audio.json", import.meta.url))).json());
  document.documentElement.style.background = "#000"; document.body.style.background = "#000"; document.body.style.margin = "0"; document.body.style.overflow = "hidden";
  R = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false, stencil: true, powerPreference: "high-performance"});
  R.setPixelRatio(1); R.setSize(W, H, false); R.setClearColor(0x000000, 1); R.toneMapping = THREE.NoToneMapping;
  uRes.value.set(W, H); uK.value = H / 720;
  S = new THREE.Scene();
  C = new THREE.PerspectiveCamera(55, W / H, 0.3, 4000);
  shapeLib();
  makeText();
  MODES[mode].build();
  const rt = new THREE.WebGLRenderTarget(W, H, {type: THREE.HalfFloatType, stencilBuffer: true});
  composer = new EffectComposer(R, rt);
  composer.addPass(new RenderPass(S, C));
  bloom = new UnrealBloomPass(new THREE.Vector2(W, H), 0.6, 0.55, 0.9);
  composer.addPass(bloom);
  fin = new ShaderPass(FIN);
  composer.addPass(fin);
}

export function frame(t, ctx) {
  const T = t0 + t;
  MODES[mode].frame(T, t);
  if (O.sky) O.sky.mesh.position.copy(C.position);
  composer.render();
}
