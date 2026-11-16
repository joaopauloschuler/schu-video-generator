// vidgen/three-kit: three.js building blocks for music videos (DESIGN.md §121.1). Part of
// schu-video-generator (MIT licence); imported by a page as "vidgen/three-kit", next to
// "vidgen/music-time" (song time, the score's events, reactions) and "vidgen/three-finish".
//
//   setStage({renderer, scene, camera, width, height});   // once in load, before anything below
//   const sky = new SkyDome(3);                             // a nebula baked once, coloured live
//   const lines = new Glow(64, {px: 1.5, world: 0.03});     // glowing strokes, a quad per segment
//   lines.seg(0, ax, ay, az, bx, by, bz); lines.col(0, color, 2); lines.flush();
//
// Light on black: lines are soft glowing strokes added to the frame (a bright core, a halo), faces
// faint glass with bright rims, skies a nebula lit from inside, and all of it meant for bloom
// (three-finish's or the page's own). Every builder adds to the stage's scene unless given
// `parent`; `inPortal: true` draws a thing only inside a portal's window (needs a renderer made
// with `stencil: true`). The look is "Parallel Space"'s (examples/parallel-space), whose code this
// is; the dust is "Escapement"'s. Nothing here is random: seeds give the same picture every time.
import * as THREE from "three";
import {clamp, smoothstep, rng, hash, lastIndex, melody} from "vidgen/music-time";

export const VERSION = 1;
const TAU = Math.PI * 2;

// ---------- the stage ----------
const STAGE = {renderer: null, scene: null, camera: null, height: 720};
// shared by every Glow: the frame's size in pixels and its height / 720 (line widths are in 720p pixels)
const uRes = {value: new THREE.Vector2(1280, 720)}, uK = {value: 1};
/** What the builders draw with: the renderer (for baking skies), the scene they add to, the camera
 * (flares, shock rings and dials face it) and the frame's size in pixels. Call once in load. */
export function setStage({renderer = null, scene, camera = null, width, height}) {
  Object.assign(STAGE, {renderer, scene, camera, height});
  uRes.value.set(width, height); uK.value = height / 720;
}
const need = (what) => { if (!STAGE[what]) throw new Error(`vidgen/three-kit: call setStage({${what}, ...}) in load first`); return STAGE[what]; };

// ---------- colours ----------
/** A colour from a hex number (sRGB; three.js converts it to linear light), times m (above 1 blooms). */
export const color = (hex, m = 1) => new THREE.Color(hex).multiplyScalar(m);
/** A new colour between a and b (u clamped to 0..1), times m. */
export const mixColor = (a, b, u, m = 1) => a.clone().lerp(b, clamp(u)).multiplyScalar(m);
/** The warm white that flashes, star cores and glints go to. */
export const WARM_WHITE = color(0xfff4e6);

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
/** Up to `max` glowing segments in one draw. Options: px (width in 720p pixels, the least it gets),
 * world (width in scene units, so near lines are wider; 0 = always px), max (widest, px), halo and
 * haloGain (the soft glow around the core), fog [near, far] (fades with distance), depthTest, order
 * (renderOrder), inPortal, parent. Width per segment is multiplied by the 4th value of col(). */
export class Glow {
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
    (o.parent ?? need("scene")).add(this.mesh);
  }
  /** Segment i from a to b. */
  seg(i, ax, ay, az, bx, by, bz) { const k = i * 3; this.a[k] = ax; this.a[k + 1] = ay; this.a[k + 2] = az; this.b[k] = bx; this.b[k + 1] = by; this.b[k + 2] = bz; }
  /** Segment i as a dot (a star). */
  dot(i, x, y, z) { this.seg(i, x, y, z, x, y, z); }
  /** Segment i's colour c times m (above 1 blooms) and width factor w. */
  col(i, c, m = 1, w = 1) { const k = i * 4; this.c[k] = c.r * m; this.c[k + 1] = c.g * m; this.c[k + 2] = c.b * m; this.c[k + 3] = w; }
  rgb(i, r, g, b, w = 1) { const k = i * 4; this.c[k] = r; this.c[k + 1] = g; this.c[k + 2] = b; this.c[k + 3] = w; }
  hide(i) { const k = i * 4; this.c[k] = this.c[k + 1] = this.c[k + 2] = 0; }
  /** Every segment's colour times c * m (a cheap way to light the whole set). */
  tint(c, m = 1) { this.mat.uniforms.uTint.value.copy(c).multiplyScalar(m); return this; }
  /** Draw only the first n segments. */
  count(n) { this.geo.instanceCount = Math.min(n, this.max); }
  /** Send what changed to the GPU: once per frame after seg()/col(). */
  flush(pos = true, col = true) { if (pos) { this.ia.needsUpdate = true; this.ib.needsUpdate = true; } if (col) this.ic.needsUpdate = true; }
  /** A fixed set of segments (pairs of points in one flat array [ax, ay, az, bx, by, bz, ...]), all one colour. */
  static from(arr, o = {}) {
    const n = arr.length / 6, g = new Glow(n, o);
    for (let i = 0; i < n; i++) g.seg(i, arr[i * 6], arr[i * 6 + 1], arr[i * 6 + 2], arr[i * 6 + 3], arr[i * 6 + 4], arr[i * 6 + 5]);
    return g;
  }
}
/** Make a material draw only where a portal's window has marked the frame (the stencil). */
export function portalOnly(mat) { mat.stencilWrite = true; mat.stencilFunc = THREE.EqualStencilFunc; mat.stencilRef = 1; mat.depthTest = false; return mat; }
/** A circle of radius r at height z as n segments (a flat array for Glow.from), starting at angle rot. */
export const circleSegments = (n, r, z = 0, rot = 0) => { const a = []; for (let i = 0; i < n; i++) { const u = rot + (i / n) * TAU, v = rot + ((i + 1) / n) * TAU; a.push(Math.cos(u) * r, Math.sin(u) * r, z, Math.cos(v) * r, Math.sin(v) * r, z); } return a; };

// ---------- glass faces and polyhedra ----------
const FACE_VERT = "varying vec3 vV; void main(){ vec4 mv = modelViewMatrix * vec4(position, 1.0); vV = mv.xyz; gl_Position = projectionMatrix * mv; }";
const FACE_FRAG = /* glsl */`
uniform vec3 uCol; uniform float uBase, uRim; varying vec3 vV;
void main(){
  vec3 n = normalize(cross(dFdx(vV), dFdy(vV))); vec3 v = normalize(-vV);
  float f = 1.0 - abs(dot(n, v));
  float facet = 0.35 + 0.65 * abs(dot(n, normalize(vec3(0.35, 0.8, 0.5))));
  gl_FragColor = vec4(uCol * (uBase * facet + uRim * f * f * f), 1.0);
}`;
/** Glass: almost nothing face-on (`base`), a bright rim at grazing angles (`rim`), added to the frame. */
export function glassMaterial(c, base = 0.05, rim = 0.5, inPortal = false) {
  const m = new THREE.ShaderMaterial({uniforms: {uCol: {value: c.clone()}, uBase: {value: base}, uRim: {value: rim}}, vertexShader: FACE_VERT, fragmentShader: FACE_FRAG,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide});
  return inPortal ? portalOnly(m) : m;
}
/** The polyhedra's names, in the order makeCrystalField and makeCrystalSwarm cycle through them. */
export const POLYHEDRA = ["octa", "tetra", "ico", "dodeca", "cube"];
const GEO = {}, EDGE = {};
function polyhedra() {
  if (GEO.ico) return;
  const g = {ico: new THREE.IcosahedronGeometry(1, 0), octa: new THREE.OctahedronGeometry(1, 0), tetra: new THREE.TetrahedronGeometry(1.15, 0),
    dodeca: new THREE.DodecahedronGeometry(1, 0), cube: new THREE.BoxGeometry(1.2, 1.2, 1.2)};
  for (const k in g) { GEO[k] = g[k]; EDGE[k] = Array.from(new THREE.EdgesGeometry(g[k], 1).attributes.position.array); }
}
const kindOf = (kind) => { polyhedra(); if (!GEO[kind]) throw new Error(`vidgen/three-kit: no polyhedron "${kind}" (${POLYHEDRA.join(", ")})`); return kind; };
/** A polyhedron's geometry (about 1 unit across), shared. */
export const polyhedronGeometry = (kind) => GEO[kindOf(kind)];
/** A polyhedron's edges as a flat array of segments (for Glow.from or Glow.seg). */
export const polyhedronEdges = (kind) => EDGE[kindOf(kind)];
/** A crystal: glass faces and glowing edges. Options: base, rim (the glass), px, world, fog, gain (edge brightness), inPortal, parent. */
export function makeCrystal(kind, lineC, faceC, o = {}) {
  const g = new THREE.Group();
  const faces = new THREE.Mesh(polyhedronGeometry(kind), glassMaterial(faceC, o.base ?? 0.05, o.rim ?? 0.55, o.inPortal)); faces.renderOrder = 4;
  const edges = Glow.from(EDGE[kind], {parent: g, px: o.px ?? 1.3, world: o.world ?? 0.035, halo: 1.2, haloGain: 0.3, fog: o.fog, inPortal: o.inPortal});
  edges.tint(lineC, o.gain ?? 1.6);
  g.add(faces); g.userData = {faces, edges, lineC: lineC.clone(), faceC: faceC.clone(), gain: o.gain ?? 1.6};
  (o.parent ?? need("scene")).add(g);
  return g;
}
/** Light a crystal: k (0..1, e.g. the kick) brightens it towards white, never changes its size; dim scales it. */
export function lightCrystal(g, k, dim = 1) {
  const u = g.userData;
  u.edges.mat.uniforms.uTint.value.copy(u.lineC).lerp(WARM_WHITE, 0.45 * k).multiplyScalar(u.gain * dim * (1 + 1.6 * k));
  u.faces.material.uniforms.uCol.value.copy(u.faceC).multiplyScalar(dim * (1 + 2.2 * k));
}

// ---------- the sky: a nebula baked into a cube map once, coloured and lit from inside every frame ----------
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
// the nebula's density, filaments, dust and stars in the four channels of a half-float cube map
function bakeNebula(seed, size) {
  const rt = new THREE.WebGLCubeRenderTarget(size, {type: THREE.HalfFloatType, magFilter: THREE.LinearFilter, minFilter: THREE.LinearFilter, generateMipmaps: false});
  const cam = new THREE.CubeCamera(1, 100, rt), sc = new THREE.Scene();
  const m = new THREE.ShaderMaterial({uniforms: {uSeed: {value: seed}}, vertexShader: SKY_VERT, fragmentShader: BAKE_FRAG, side: THREE.BackSide, depthTest: false, depthWrite: false});
  sc.add(new THREE.Mesh(new THREE.BoxGeometry(20, 20, 20), m));
  cam.update(need("renderer"), sc);
  m.dispose();
  return rt.texture;
}
function skyUniforms(tex) {
  return {uSky: {value: tex}, uM1: {value: new THREE.Matrix3()}, uM2: {value: new THREE.Matrix3()},
    uA: {value: color(0x010308)}, uB: {value: color(0x06203a)}, uC: {value: color(0x2a7fa0)},
    uL1: {value: new THREE.Vector3(0, 0, -1)}, uL1c: {value: new THREE.Color(0, 0, 0)}, uL1p: {value: 6},
    uL2: {value: new THREE.Vector3(0, 1, 0)}, uL2c: {value: new THREE.Color(0, 0, 0)}, uL2p: {value: 6},
    uLo: {value: 0.32}, uHi: {value: 0.72}, uStar: {value: 1}, uDust: {value: 0.6}, uGain: {value: 1}};
}
const M4 = new THREE.Matrix4(), EUL = new THREE.Euler();
/** A nebula with stars all around the camera, baked once from `seed` (cube faces of `size` px: default
 * 640 for a frame 600 px tall or more, else 256). Each frame: turn(T) drifts it, colors() sets its
 * deep / mid / bright colours and gain, light() places two lights inside it, follow(camera) keeps it
 * centred on the camera. */
export class SkyDome {
  constructor(seed, {size = null, parent = null} = {}) {
    this.u = skyUniforms(bakeNebula(seed, size ?? (STAGE.height >= 600 ? 640 : 256)));
    this.mesh = new THREE.Mesh(new THREE.BoxGeometry(2000, 2000, 2000), new THREE.ShaderMaterial({uniforms: this.u, vertexShader: SKY_VERT, fragmentShader: SKY_FRAG, side: THREE.BackSide, depthTest: false, depthWrite: false}));
    this.mesh.frustumCulled = false; this.mesh.renderOrder = -10; (parent ?? need("scene")).add(this.mesh);
  }
  /** The two layers of the nebula turned slowly with song time T (k: how fast). */
  turn(T, k = 1) {
    this.u.uM1.value.setFromMatrix4(M4.makeRotationFromEuler(EUL.set(0.2 + T * 0.0031 * k, 0.6 + T * 0.0047 * k, 0.1)));
    this.u.uM2.value.setFromMatrix4(M4.makeRotationFromEuler(EUL.set(1.3 - T * 0.0043 * k, 2.1 + T * 0.0022 * k, 0.7 + T * 0.0035 * k)));
  }
  /** Colours of empty space (a), thin gas (b) and dense gas (c), and the whole sky's gain. */
  colors(a, b, c, gain = 1) { const u = this.u; u.uA.value.copy(a); u.uB.value.copy(b); u.uC.value.copy(c); u.uGain.value = gain; }
  /** Light n (1 or 2) from direction dir in colour c times m; pow: how tight (higher = smaller). */
  light(n, dir, c, m, pow = 6) { const u = this.u; (n === 1 ? u.uL1 : u.uL2).value.copy(dir).normalize(); (n === 1 ? u.uL1c : u.uL2c).value.copy(c).multiplyScalar(m); (n === 1 ? u.uL1p : u.uL2p).value = pow; }
  follow(camera) { this.mesh.position.copy(camera.position); }
}

// ---------- a portal: a ring with a window onto another sky ----------
const WIN_VERT = "varying vec3 vD; void main(){ vec4 w = modelMatrix * vec4(position, 1.0); vD = w.xyz - cameraPosition; gl_Position = projectionMatrix * viewMatrix * w; }";
/** A ring of light of `radius` whose window shows `sky` (a SkyDome, usually hidden: `sky.mesh.visible = false`)
 * and marks the stencil, so things made with `inPortal: true` show only through it; a rim and a dial of 48 marks around it. */
export function makePortal(radius, sky, o = {}) {
  const g = new THREE.Group();
  const u = skyUniforms(sky.u.uSky.value);
  for (const k in u) if (k !== "uGain") u[k] = sky.u[k];
  u.uGain = {value: 1};
  const win = new THREE.Mesh(new THREE.CircleGeometry(radius, 72), new THREE.ShaderMaterial({uniforms: u, vertexShader: WIN_VERT, fragmentShader: SKY_FRAG, side: THREE.DoubleSide}));
  win.material.stencilWrite = true; win.material.stencilFunc = THREE.AlwaysStencilFunc; win.material.stencilRef = 1; win.material.stencilZPass = THREE.ReplaceStencilOp;
  win.renderOrder = -5; g.add(win);
  const ring = Glow.from(circleSegments(96, radius), {parent: g, px: 2.2, world: radius * 0.035, halo: 1.6, haloGain: 0.4, fog: o.fog});
  const rim = Glow.from(circleSegments(96, radius * 1.07), {parent: g, px: 1.0, world: radius * 0.008, halo: 1.2, haloGain: 0.3, fog: o.fog});
  const marks = [];
  for (let i = 0; i < 48; i++) { const a = (i / 48) * TAU, r0 = radius * 1.11, r1 = radius * (i % 4 === 0 ? 1.2 : 1.15); marks.push(Math.cos(a) * r0, Math.sin(a) * r0, 0, Math.cos(a) * r1, Math.sin(a) * r1, 0); }
  const dial = Glow.from(marks, {parent: g, px: 1.1, world: radius * 0.01, halo: 1.2, haloGain: 0.3, fog: o.fog});
  g.userData = {win, ring, rim, dial, radius, u};
  (o.parent ?? need("scene")).add(g);
  return g;
}
/** The portal's ring in ringC times m, its rim, and its window's brightness. */
export function lightPortal(p, ringC, m, rimC = WARM_WHITE, rm = 0.6, winGain = 1) { const u = p.userData; u.ring.tint(ringC, m); u.rim.tint(rimC, rm); u.u.uGain.value = winGain; }
/** Light a portal's dial like a clock: `step` is the mark of now (e.g. the count of eighths), `e` how bright it is; the five before it fade. */
export function lightDial(p, c, base, step, e, n = 48) {
  const d = p.userData.dial;
  for (let i = 0; i < n; i++) { const back = ((step - i) % n + n) % n; d.col(i, c, base + (back < 6 ? e * Math.pow(0.55, back) * 3 : 0)); }
  d.flush(false, true);
}

// ---------- the tesseract: 16 corners, 32 edges, turned in 4D and projected ----------
export const TESSERACT_VERTICES = [], TESSERACT_EDGES = [];
for (let i = 0; i < 16; i++) TESSERACT_VERTICES.push([(i & 1) ? 1 : -1, (i & 2) ? 1 : -1, (i & 4) ? 1 : -1, (i & 8) ? 1 : -1]);
for (let i = 0; i < 16; i++) for (let j = i + 1; j < 16; j++) { let d = 0; for (let k = 0; k < 4; k++) if (TESSERACT_VERTICES[i][k] !== TESSERACT_VERTICES[j][k]) d++; if (d === 1) TESSERACT_EDGES.push([i, j]); }
const PLANES = [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]];
/** A 4D point v turned by the six plane angles `angs` (xy, xz, xw, yz, yw, zw) and seen from distance `dist` in w: [x, y, z]. */
export function project4(v, angs, dist = 3.1, out = [0, 0, 0]) {
  const p = [v[0], v[1], v[2], v[3]];
  for (let i = 0; i < 6; i++) { const a = angs[i]; if (!a) continue; const c = Math.cos(a), s = Math.sin(a), i0 = PLANES[i][0], i1 = PLANES[i][1], u = p[i0], w = p[i1]; p[i0] = u * c - w * s; p[i1] = u * s + w * c; }
  const den = dist - p[3], sc = dist / (Math.abs(den) < 1e-3 ? 1e-3 : den);
  out[0] = p[0] * sc; out[1] = p[1] * sc; out[2] = p[2] * sc; return out;
}
/** Six slow, unrelated turning speeds: the tesseract's angles at time T (extra adds a turn in two planes). */
export const tesseractAngles = (T, extra = 0) => [T * 0.31 + extra, T * 0.19, T * 0.41 + extra * 0.5, T * 0.23, T * 0.37, T * 0.29];
/** A tesseract of glowing edges (and its 16 corners as stars). Options: px, world, fog, inPortal, parent. */
export function makeTesseract(o = {}) {
  const g = new THREE.Group();
  const gl = new Glow(48, {parent: g, px: o.px ?? 1.6, world: o.world ?? 0.03, halo: 1.5, haloGain: 0.35, inPortal: o.inPortal, fog: o.fog});
  g.userData = {gl, P: TESSERACT_VERTICES.map(() => [0, 0, 0])};
  (o.parent ?? need("scene")).add(g);
  return g;
}
/** Edges in colour c (the inner cube's dimmer), corners as warm white stars of nodeGain. */
export function updateTesseract(tes, angs, c, gain = 1.6, nodeGain = 2.5) {
  const {gl, P} = tes.userData;
  TESSERACT_VERTICES.forEach((v, i) => project4(v, angs, 3.1, P[i]));
  TESSERACT_EDGES.forEach((e, i) => {
    const a = P[e[0]], b = P[e[1]];
    gl.seg(i, a[0], a[1], a[2], b[0], b[1], b[2]);
    const size = (Math.hypot(a[0], a[1], a[2]) + Math.hypot(b[0], b[1], b[2])) * 0.5;      // 1.3 (inner cube) .. 2.6 (outer)
    gl.col(i, c, gain * (0.35 + 0.65 * smoothstep(1.1, 2.4, size)));
  });
  for (let i = 0; i < 16; i++) { gl.dot(32 + i, P[i][0], P[i][1], P[i][2]); gl.col(32 + i, WARM_WHITE, nodeGain, 2.6); }
  gl.flush();
}

// ---------- stars and dust with depth: points that wrap along the flight axis (-z) ----------
/** Where a point that starts z0 ahead lies after the camera (at camZ) has flown `dist`: between near and depth ahead, wrapping. */
export function wrapZ(z0, dist, depth, camZ = 0, near = 8) { const span = Math.max(1, depth - near); let u = (z0 + dist) % span; if (u < 0) u += span; return camZ - near - u; }
const STAR_TINTS = [WARM_WHITE, WARM_WHITE, color(0x9fdcff), color(0x9fdcff), color(0x35e8ff), color(0x9b5cff)];
/** n stars in a tube around the flight axis (radius rad[0]..rad[1], depth deep), seeded. Options: px, world, fog, tints, inPortal. */
export function makeStarField(n, rad, depth, seed, o = {}) {
  const r = rng(seed), gl = new Glow(n, {px: o.px ?? 1.5, halo: 1.3, haloGain: 0.45, world: o.world ?? 0, fog: o.fog, order: 2, inPortal: o.inPortal});
  const base = [], tints = o.tints ?? STAR_TINTS;
  for (let i = 0; i < n; i++) {
    const a = r() * TAU, d = rad[0] + (rad[1] - rad[0]) * Math.sqrt(r());
    const c = tints[Math.floor(r() * tints.length)], m = 0.25 + 1.5 * Math.pow(r(), 2.4), w = 0.6 + 1.3 * Math.pow(r(), 3);
    base.push([Math.cos(a) * d, Math.sin(a) * d, r() * depth, m, w, r() * TAU, c]);
  }
  return {gl, base, depth, n};
}
/** The stars after flying `dist`: twinkling, faded in far away and near, stretched into streaks of `streak` units (speed). */
export function updateStarField(st, T, dist, streak = 0, camZ = 0, gain = 1, near = 10) {
  const {gl, base, depth} = st, edge = depth * 0.12;
  for (let i = 0; i < base.length; i++) {
    const b = base[i], z = wrapZ(b[2], dist, depth, camZ, near), dz = camZ - z;
    const fade = smoothstep(depth, depth - edge, dz) * smoothstep(near, near + edge * 0.3, dz);
    const tw = 0.75 + 0.25 * Math.sin(T * (1.3 + (i % 7) * 0.31) + b[5]);
    gl.seg(i, b[0], b[1], z, b[0], b[1], z - streak);
    gl.col(i, b[6], b[3] * fade * tw * gain, b[4]);
  }
  gl.flush();
}
/** n still stars all around (a shell of radius r0..r1, squashed by `flat`), for a camera circling a centre. Options: px, tints, flat, inPortal. */
export function makeStarShell(n, r0, r1, seed, o = {}) {
  const r = rng(seed), gl = new Glow(n, {px: o.px ?? 1.5, halo: 1.3, haloGain: 0.45, order: 2, inPortal: o.inPortal}), tints = o.tints ?? STAR_TINTS;
  for (let i = 0; i < n; i++) {
    const z = r() * 2 - 1, a = r() * TAU, q = Math.sqrt(1 - z * z), d = r0 + (r1 - r0) * Math.pow(r(), 0.7);
    gl.dot(i, Math.cos(a) * q * d, z * d * (o.flat ?? 1), Math.sin(a) * q * d);
    gl.col(i, tints[Math.floor(r() * tints.length)], 0.25 + 1.5 * Math.pow(r(), 2.4), 0.6 + 1.3 * Math.pow(r(), 3));
  }
  gl.flush();
  return gl;
}

// ---------- light itself: a flare (glow, a horizontal streak, slow rays) facing the camera ----------
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
/** A flare of `size` units. Options: streak, rays, depthTest, order, inPortal, parent. */
export function makeFlare(size, o = {}) {
  const m = new THREE.ShaderMaterial({uniforms: {uCol: {value: new THREE.Color(1, 1, 1)}, uI: {value: 1}, uStreak: {value: o.streak ?? 0.8}, uRays: {value: o.rays ?? 0.25}, uRot: {value: 0}},
    vertexShader: FLARE_VERT, fragmentShader: FLARE_FRAG, transparent: true, depthWrite: false, depthTest: o.depthTest ?? true, blending: THREE.AdditiveBlending});
  if (o.inPortal) portalOnly(m);
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(size, size), m); mesh.renderOrder = o.order ?? 3; mesh.frustumCulled = false;
  (o.parent ?? need("scene")).add(mesh);
  return mesh;
}
/** The flare's colour, intensity, rays' turn and scale; it is turned to face the stage's camera. */
export function setFlare(f, c, i, rot = 0, scale = 1) { const u = f.material.uniforms; u.uCol.value.copy(c); u.uI.value = i; u.uRot.value = rot; f.scale.setScalar(scale); f.quaternion.copy(need("camera").quaternion); }

// ---------- rings of light that spread from a hit ----------
/** n unit circles of glowing line, one for each of the last n hits. */
export function makeShockRings(n, seg = 96) { const a = []; for (let i = 0; i < n; i++) a.push(Glow.from(circleSegments(seg, 1), {px: 1.4, world: 0.02, halo: 2.0, haloGain: 0.4})); return a; }
const V3 = new THREE.Vector3();
/** One ring per recent hit of the track ({t, g}, music-time's trackArrays): it grows from r0 by up to r1
 * over `life` s and fades. Options: at (centre), r0, r1, life, gain, face (turn to the camera), only(time) (which hits). */
export function updateShockRings(shocks, hits, T, c, o = {}) {
  const h = hits, last = h ? lastIndex(h.t, T) : -1;
  shocks.forEach((s, k) => {
    const j = last - k, age = j >= 0 ? T - h.t[j] : 1e9, life = o.life ?? 3.5;
    if (age > life || (o.only && !o.only(h.t[j]))) { s.mesh.visible = false; return; }
    s.mesh.visible = true;
    const u = age / life, r = (o.r0 ?? 3) + (o.r1 ?? 70) * (1 - Math.pow(1 - u, 2.2));
    s.mesh.scale.setScalar(r); s.mesh.position.copy(o.at ?? V3.set(0, 0, 0)); if (o.face) s.mesh.quaternion.copy(need("camera").quaternion);
    s.mat.uniforms.uWorld.value = 0.012 + 0.03 * u;
    s.tint(c, (o.gain ?? 3) * Math.pow(1 - u, 1.6) * Math.min(h.g[j], 1.3));
  });
}

// ---------- notes as glints: each note lights a small four-pointed star for a while ----------
/** For the last n notes of the track ({t, d, p}) younger than `life` s: a star at place(index, pitch)
 * ([x, y, z]) with four rays, rising over `rise` s and fading. gl needs 5 * n segments. Options: n,
 * life, rise, c (rays' colour), size, gain, place (required). */
export function updateGlints(gl, notes, T, o = {}) {
  const ns = notes, bi = ns ? lastIndex(ns.t, T) : -1, n = o.n ?? 12, life = o.life ?? 5, c = o.c ?? WARM_WHITE;
  for (let k = 0; k < n; k++) {
    const j = bi - k, base = k * 5;
    if (j < 0 || T - ns.t[j] > life) { for (let q = 0; q < 5; q++) gl.hide(base + q); continue; }
    const age = T - ns.t[j], e = Math.exp(-age / (life * 0.32)) * clamp(age / (o.rise ?? 0.02)), P = o.place(j, ns.p[j]), s = (o.size ?? 2.2) * (e + 0.2);
    const x = P[0], y = P[1], z = P[2];
    gl.dot(base, x, y, z); gl.col(base, WARM_WHITE, (o.gain ?? 5) * e, 2.4);
    gl.seg(base + 1, x - s * 2, y, z, x + s * 2, y, z); gl.seg(base + 2, x, y - s, z, x, y + s, z);
    gl.seg(base + 3, x - s * 0.5, y - s * 0.5, z, x + s * 0.5, y + s * 0.5, z); gl.seg(base + 4, x - s * 0.5, y + s * 0.5, z, x + s * 0.5, y - s * 0.5, z);
    for (let q = 1; q < 5; q++) gl.col(base + q, c, (q < 3 ? 1.6 : 0.7) * e * (o.gain ?? 5) / 5, 0.7);
  }
  gl.flush();
}

// ---------- the melody as a line of light ----------
/** A ribbon of n segments (and a bright head). Options: px, world, max, parent, inPortal. */
export function makeRibbon(n, o = {}) { return new Glow(n + 1, {px: o.px ?? 1.8, world: o.world ?? 0.3, halo: 1.8, haloGain: 0.4, max: o.max ?? 6, parent: o.parent, inPortal: o.inPortal}); }
const RA = [0, 0, 0], RB = [0, 0, 0];
/** `span` seconds of the melody of the notes track drawn as a line: pos(time, pitch, age, out) places
 * each moment; colour from cA (now) to cB (older), fading with age over tau s; the pitch glides over `glide` s. */
export function updateRibbon(gl, notes, T, span, pos, cA, cB, gain = 3, tau = 3, glide = 0.2) {
  const n = gl.max - 1, dt = span / n;
  let m0 = melody(notes, T, glide); pos(T, m0[0], 0, RA);
  gl.dot(n, RA[0], RA[1], RA[2]); gl.col(n, WARM_WHITE, gain * 1.6 * m0[1], 2.8);
  for (let i = 0; i < n; i++) {
    const age = (i + 1) * dt, m1 = melody(notes, T - age, glide); pos(T - age, m1[0], age, RB);
    gl.seg(i, RA[0], RA[1], RA[2], RB[0], RB[1], RB[2]);
    gl.col(i, mixColor(cA, cB, age / span * 1.4), gain * Math.min(m0[1], m1[1]) * Math.exp(-age / tau), 1 + 0.8 * Math.exp(-age * 3));
    RA[0] = RB[0]; RA[1] = RB[1]; RA[2] = RB[2]; m0 = m1;
  }
  gl.flush();
}

// ---------- the spectrum as rays about a centre ----------
/** 96 rays: 16 bands, mirrored, three times round. Options: px, world, inPortal. */
export function makeSpectrumRays(parent, o = {}) { return new Glow(96, {parent, px: o.px ?? 2.0, world: o.world ?? 1.0, halo: 1.3, haloGain: 0.3, max: 8, inPortal: o.inPortal}); }
/** Rays from radius r0, each `len` * (0.06 + its band) long; band(b) gives band b (0..15) now (e.g. ctx.music.band). */
export function updateSpectrumRays(gl, band, r0, len, cA, cB, gain = 1.6) {
  for (let i = 0; i < 96; i++) {
    const m = i % 32, b = m < 16 ? m : 31 - m, a = (i / 96) * TAU + Math.PI / 2, h = band(b), r1 = r0 + len * (0.06 + h), c = Math.cos(a), s = Math.sin(a);
    gl.seg(i, c * r0, s * r0, 0, c * r1, s * r1, 0); gl.col(i, mixColor(cA, cB, b / 15), gain * (0.35 + 1.1 * h));
  }
  gl.flush();
}

// ---------- tunnels and corridors ----------
/** Rings flying past on the beat: one polygon for every `per` seconds still ahead (gl holds 8 segments per
 * ring). zOf(time) is where that moment lies on the flight axis; look(index, time) gives [colour, gain,
 * sides (3..8)]; far: how far ahead they fade in; rad: their radius. */
export function updateTunnel(gl, T, per, zOf, far, rad, look) {
  const first = Math.floor(T / per + 1e-6) + 1, count = Math.floor(gl.max / 8);
  for (let j = 0; j < count; j++) {
    const idx = first + j, tk = idx * per, z = zOf(tk), L = look(idx, tk), sides = L[2];
    const fade = smoothstep(-far, -far * 0.65, z) * smoothstep(-4, -18, z), rot = tk * 0.5 + (idx % 2 ? Math.PI / sides : 0);
    for (let q = 0; q < 8; q++) {
      const i = j * 8 + q;
      if (q >= sides) { gl.hide(i); continue; }
      const a = rot + (q / sides) * TAU, b = rot + ((q + 1) / sides) * TAU;
      gl.seg(i, Math.cos(a) * rad, Math.sin(a) * rad, z, Math.cos(b) * rad, Math.sin(b) * rad, z); gl.col(i, L[0], L[1] * fade);
    }
  }
  gl.flush();
}
/** A corridor: a twisting truss of N hexagons `spacing` apart, joined by struts, wrapped along the flight axis. Options: world, twist, inPortal. */
export function makeLattice(N = 14, spacing = 22, radius = 11, o = {}) {
  const gl = new Glow(N * 18, {px: 1.2, world: o.world ?? 0.05, halo: 1.5, haloGain: 0.3, max: 4, inPortal: o.inPortal});
  return {gl, N, spacing, radius, depth: N * spacing, twist: o.twist ?? Math.PI / 9};
}
/** The corridor after flying `dist`: cellGain(i, distanceAhead) lights each hexagon (a light running down it
 * is a gain that depends on the distance); struts are `strut` times dimmer. */
export function updateLattice(lat, T, dist, camZ, c, cellGain, strut = 0.45) {
  const {gl, N, spacing, radius, depth, twist} = lat;
  for (let i = 0; i < N; i++) {
    const zc = wrapZ(i * spacing, dist, depth, camZ, 0), ahead = camZ - zc;
    const lap = Math.floor((i * spacing + dist) / depth), rot = (i - lap * N) * twist, g = cellGain(i, ahead) * smoothstep(depth, depth * 0.75, ahead) * smoothstep(-2, 6, ahead);
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
/** Great rings turning slowly about one centre, each with marks like an instrument's scale. Options: radii, inPortal. */
export function makeRingStructure(o = {}) {
  const g = new THREE.Group(), rings = [];
  (o.radii ?? [34, 70, 118, 186, 280]).forEach((r, k) => {
    const h = new THREE.Group(), pts = circleSegments(160, r);
    const n = 24 + k * 12; for (let i = 0; i < n; i++) { const a = (i / n) * TAU, r1 = r * (i % 6 === 0 ? 1.06 : 1.03); pts.push(Math.cos(a) * r, Math.sin(a) * r, 0, Math.cos(a) * r1, Math.sin(a) * r1, 0); }
    pts.push(...circleSegments(160, r * 0.985));
    const gl = Glow.from(pts, {parent: h, px: 1.3, world: r * 0.004, halo: 1.5, haloGain: 0.35, max: 5, inPortal: o.inPortal});
    g.add(h); rings.push({h, gl, r});
  });
  need("scene").add(g);
  return {g, rings};
}
/** Turn the rings with T; c and gain are values or functions of the ring's number. */
export function updateRingStructure(m, T, c, gain, spin = 1) {
  m.rings.forEach((q, k) => {
    q.h.rotation.set(0.5 + k * 0.55 + T * 0.021 * spin * (k % 2 ? -1 : 1), k * 0.9 + T * 0.017 * spin, T * 0.03 * spin * (k % 2 ? 1 : -1));
    q.gl.tint(typeof c === "function" ? c(k) : c, typeof gain === "function" ? gain(k) : gain);
  });
}

// ---------- crystals in numbers ----------
/** n crystals along the flight axis (radius rad[0]..rad[1], depth deep), coloured from the palette `pal`.
 * Options: kinds (how many of POLYHEDRA), gain, world, s0 and s1 (sizes), flat, inPortal. */
export function makeCrystalField(n, rad, depth, seed, pal, o = {}) {
  const r = rng(seed), list = [];
  for (let i = 0; i < n; i++) {
    const a = r() * TAU, d = rad[0] + r() * (rad[1] - rad[0]);
    const g = makeCrystal(POLYHEDRA[i % (o.kinds ?? 3)], pal[i % pal.length], pal[(i + 1) % pal.length], {gain: o.gain ?? 1.5, inPortal: o.inPortal, world: o.world ?? 0.04});
    g.userData.f = {x: Math.cos(a) * d, y: Math.sin(a) * d * (o.flat ?? 1), z0: r() * depth, s: (o.s0 ?? 0.5) + r() * (o.s1 ?? 1.6), spin: 0.12 + r() * 0.5, band: i % 16, pulse: i % 2 === 0, ph: r() * TAU};
    list.push(g);
  }
  return {list, depth};
}
/** The field after flying `dist`: every other crystal lit by k (e.g. the kick), the others by their band(b) (0..15). */
export function updateCrystalField(f, T, dist, k, band, camZ = 0, gain = 1, near = 14) {
  const edge = f.depth * 0.15;
  f.list.forEach((g) => {
    const u = g.userData.f, z = wrapZ(u.z0, dist, f.depth, camZ, near), dz = camZ - z;
    g.position.set(u.x, u.y, z); g.scale.setScalar(u.s);
    g.rotation.set(T * u.spin + u.ph, T * u.spin * 1.35, u.ph);
    lightCrystal(g, u.pulse ? k : 0.25 * band(u.band), gain * smoothstep(f.depth, f.depth - edge, dz) * smoothstep(near, near + 10, dz));
  });
}
/** n crystals on slow orbits about the origin (radius rad[0]..rad[1]). Options: tilt, gain, world, s0, s1, inPortal. */
export function makeCrystalSwarm(n, rad, seed, pal, o = {}) {
  const r = rng(seed), list = [];
  for (let i = 0; i < n; i++) {
    const g = makeCrystal(POLYHEDRA[i % 5], pal[i % pal.length], pal[(i + 1) % pal.length], {gain: o.gain ?? 1.5, world: o.world ?? 0.06, inPortal: o.inPortal});
    const ax = new THREE.Vector3(r() * 2 - 1, (r() * 2 - 1) * (o.tilt ?? 2.5), r() * 2 - 1).normalize();
    const u = new THREE.Vector3(1, 0, 0).cross(ax).normalize(), v = ax.clone().cross(u);
    const d = rad[0] + (rad[1] - rad[0]) * Math.pow(r(), 1.3);
    g.userData.o = {u, v, d, ph: r() * TAU, w: (0.05 + 0.1 * r()) * Math.sqrt(40 / d) * (r() < 0.5 ? -1 : 1), s: (o.s0 ?? 0.6) + r() * (o.s1 ?? 1.6), spin: 0.1 + r() * 0.4, band: i % 16, pulse: i % 2 === 0};
    list.push(g);
  }
  return list;
}
/** The swarm at T: every other crystal lit by k, the others by 0.3 * band(b); spread scales the orbits. */
export function updateCrystalSwarm(list, T, k, band, gain = 1, spread = 1) {
  list.forEach((g) => {
    const o = g.userData.o, a = o.ph + T * o.w, c = Math.cos(a) * o.d * spread, s = Math.sin(a) * o.d * spread;
    g.position.set(o.u.x * c + o.v.x * s, o.u.y * c + o.v.y * s, o.u.z * c + o.v.z * s); g.scale.setScalar(o.s);
    g.rotation.set(T * o.spin + o.ph, T * o.spin * 1.35, o.ph);
    lightCrystal(g, o.pulse ? k : 0.3 * band(o.band), gain);
  });
}

// ---------- dust: soft points drifting in a box ----------
/** A soft round dot (white, alpha falling from 1 at the centre through `middle` = [radius, alpha] to 0 at the edge) as a texture. */
export function softDotTexture(size = 128, middle = [0.35, 0.35]) {
  const c = document.createElement("canvas"); c.width = c.height = size; const g = c.getContext("2d");
  const grd = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grd.addColorStop(0, "rgba(255,255,255,1)"); grd.addColorStop(middle[0], `rgba(255,255,255,${middle[1]})`); grd.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grd; g.fillRect(0, 0, size, size);
  return new THREE.CanvasTexture(c);
}
/** n motes of `size` units in a box [width, height, depth, cx, cy, cz], placed by `seed`; updateDustCloud moves them. */
export function makeDustCloud(n, box, size, seed = 1) {
  const pos = new Float32Array(n * 3), g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const m = new THREE.PointsMaterial({map: softDotTexture(), size, sizeAttenuation: true, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, color: 0xffffff});
  const pts = new THREE.Points(g, m); pts.frustumCulled = false; need("scene").add(pts);
  return {pts, pos, n, box, seed};
}
/** The dust at T: each mote drifts by `drift` units a second on its own heading, wrapping in the box; colour col times amt. */
export function updateDustCloud(d, T, col, amt, drift = 0.15) {
  const [bx, by, bz, cx, cy, cz] = d.box;
  for (let i = 0; i < d.n; i++) {
    const wrap = (v, w) => ((v % w) + w) % w - w / 2;
    d.pos[i * 3] = cx + wrap(hash(i, d.seed) * bx + T * drift * (hash(i, d.seed + 7) - 0.5), bx);
    d.pos[i * 3 + 1] = cy + wrap(hash(i, d.seed + 1) * by + T * drift * (hash(i, d.seed + 8) - 0.5), by);
    d.pos[i * 3 + 2] = cz + wrap(hash(i, d.seed + 2) * bz + T * drift * 0.6 * (hash(i, d.seed + 9) - 0.2), bz);
  }
  d.pts.geometry.attributes.position.needsUpdate = true; d.pts.material.color.copy(col).multiplyScalar(amt);
}

// ---------- the camera ----------
/** Put the stage's camera at (x, y, z) looking at (lx, ly, lz), rolled by `roll` radians, with vertical field of view `fov` degrees. */
export function aimCamera(x, y, z, lx, ly, lz, roll = 0, fov = 55) {
  const C = need("camera");
  C.position.set(x, y, z); C.up.set(Math.sin(roll), Math.cos(roll), 0); C.lookAt(lx, ly, lz);
  if (Math.abs(C.fov - fov) > 1e-3) { C.fov = fov; C.updateProjectionMatrix(); }
  C.updateMatrixWorld();
}
