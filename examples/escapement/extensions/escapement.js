// Escapement: one three.js module for every scene of the film (data.mode picks the shot).
//
// Everything is a function of the song time T = ctx.music.t0 + t. The music is 120 BPM, so one beat is
// exactly 15 frames at 30 fps and one bar exactly 60: the escapement ticks on the beat and nothing
// drifts. No state is carried from frame to frame or from scene to scene and nothing is random, so a
// scene renders the same every time, in any order.
//
// The watch is a real (if imaginary) calibre, in millimetres, with a going train whose speeds come
// from its tooth counts:
//   barrel 72 -> centre pinion 9 (8:1) | centre wheel 64 -> third pinion 8 (8:1) |
//   third wheel 60 -> fourth pinion 8 (7.5:1) | fourth wheel 48 -> escape pinion 12 (4:1) |
//   escape wheel 15 teeth, one tooth every two beats; the balance swings once a second (7,200 A/h).
// So the fourth wheel (the seconds hand) turns once a minute, the centre wheel (the minute hand) once
// an hour, the barrel once in eight hours, and the motion work (12 -> 36, 10 -> 40) gives the hour
// hand its 12:1. Every pair is in mesh: tooth in gap, neighbours counter-rotating. The mechanism's
// beats are read from the score (ctx.music: the score's own ticks), so where the music's tick
// falters or stops for a bar, the balance does too.
//
// The look: brass, rhodium, blued steel and ruby as physically based metal under a studio of soft
// boxes baked once into an environment map, one shadowed key light, a thin depth of field, bloom on
// the highlights only, a filmic tone curve, a colour grade per shot, vignette and fine grain.
// Hits pulse the light, never the camera.
import * as THREE from "three";
import {EffectComposer} from "three/addons/postprocessing/EffectComposer.js";
import {UnrealBloomPass} from "three/addons/postprocessing/UnrealBloomPass.js";
import {ShaderPass} from "three/addons/postprocessing/ShaderPass.js";
import {Pass, FullScreenQuad} from "three/addons/postprocessing/Pass.js";
import * as BGU from "three/addons/utils/BufferGeometryUtils.js";

const BAR = 2, BEAT = 0.5, S16 = BAR / 16, TAU = Math.PI * 2, DEG = Math.PI / 180;
let R, S, C, composer, scenePass, bloom, fin, aa, W, H, AU, mode, t0, PM;
let titleEl, endEl, Q = {};
const O = {};

// ---------- small helpers ----------
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const mix = (a, b, u) => a + (b - a) * u;
const sstep = (a, b, x) => { const u = clamp((x - a) / (b - a)); return u * u * (3 - 2 * u); };
const ease = (u) => { u = clamp(u); return u * u * u * (u * (u * 6 - 15) + 10); };
const easeOut = (u) => 1 - Math.pow(1 - clamp(u), 3);
const hash1 = (i, k = 0) => { const x = Math.sin(i * 127.1 + k * 311.7 + 0.5) * 43758.5453; return x - Math.floor(x); };
const hx = (hex, m = 1) => new THREE.Color(hex).multiplyScalar(m);
const TMPC = new THREE.Color();
const lc = (a, b, u, m = 1) => TMPC.copy(a).lerp(b, clamp(u)).multiplyScalar(m).clone();
const V2 = (x, y) => new THREE.Vector2(x, y);
const pol = (r, a) => new THREE.Vector2(r * Math.cos(a), r * Math.sin(a));
function arcPts(r, a0, a1, n, cx = 0, cy = 0) { const p = []; for (let i = 0; i <= n; i++) { const a = a0 + (a1 - a0) * i / n; p.push(V2(cx + r * Math.cos(a), cy + r * Math.sin(a))); } return p; }

// ---------- the music as data ----------
// vidgen hands the page the score's events (video.yaml: `music_data`), read here into sorted time
// arrays per track: when each drum and click is struck (t, gain) and every note (t, length, pitch).
// Times are kept on the score's grid of sixteenths to three decimals (`grid`), as the film's own
// exporter wrote them: the triplet strokes of the three-against-four work then fall 42 microseconds
// from where ctx.music puts them, and the hammers move exactly as in the published film.
const HIT_TRACKS = ["tick", "tock", "ratchet", "boom", "taiko", "tom", "three", "hat", "chime"];
const NOTE_TRACKS = ["box", "horn", "lead", "cell", "chime", "twinkle", "pend", "counter"];
// The mechanism's beats: every quarter note from START_BAR, except in the FALTER bars (there the
// score's own tick and tock are used as written) and inside the SILENT_BAR (one tick on its first
// beat, then nothing until the next bar).
const START_BAR = 4, FALTER = [56, 60], SILENT_BAR = 67;
const grid = (x) => Math.round(x / S16 * 1000) / 1000 * S16;
function fromMusic(M) {
  const hits = {}, notes = {};
  for (const k of HIT_TRACKS) {
    const h = M.events(k); hits[k] = {t: Float32Array.from(h, (e) => grid(e.time)), g: Float32Array.from(h, (e) => e.gain)};
  }
  for (const k of NOTE_TRACKS) {
    const list = M.events(k); notes[k] = {t: Float32Array.from(list, (e) => grid(e.time)), d: Float32Array.from(list, (e) => grid(e.duration)), p: Float32Array.from(list, (e) => e.pitch ?? 0)};
  }
  const bar = M.score.bar, f0 = FALTER[0] * bar, f1 = FALTER[1] * bar, s0 = SILENT_BAR * bar, s1 = s0 + bar;
  const end = bar * M.score.sections.reduce((a, s) => a + Math.round((s.end - s.start) / bar), 0);
  const beats = new Set();
  for (let s = START_BAR * bar; s <= end + 1e-9; s += M.score.beat) if (!(s >= f0 - 1e-9 && s < f1 - 1e-9) && !(s > s0 + 1e-9 && s < s1 - 1e-9)) beats.add(+s.toFixed(6));
  for (const k of ["tick", "tock"]) for (const e of M.events(k, f0, f1)) beats.add(+e.time.toFixed(6));
  return {hits, notes, beats: Float64Array.from([...beats].sort((a, b) => a - b))};
}
function lastIdx(ts, T) { let lo = 0, hi = ts.length - 1, k = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (ts[m] <= T + 1e-5) { k = m; lo = m + 1; } else hi = m - 1; } return k; }
// the envelope of a drum: 1 (more on an accent) at each hit, falling with `decay` seconds
function env(name, T, decay) {
  const h = AU.hits[name]; if (!h) return 0;
  let v = 0;
  for (let j = lastIdx(h.t, T), n = 0; j >= 0 && n < 3; j--, n++) v = Math.max(v, Math.min(h.g[j], 1.25) * Math.exp(-(T - h.t[j]) / decay));
  return v;
}
function hitCount(name, T) { const h = AU.hits[name]; return h ? lastIdx(h.t, T) + 1 : 0; }
function hitAge(name, T) { const h = AU.hits[name]; const i = h ? lastIdx(h.t, T) : -1; return i < 0 ? 1e9 : T - h.t[i]; }
function note(name, T) { const n = AU.notes[name], i = n ? lastIdx(n.t, T) : -1; return i < 0 ? null : {i, p: n.p[i], age: T - n.t[i], d: n.d[i]}; }
function noteEnv(name, T, decay) { const q = note(name, T); return q ? Math.exp(-q.age / decay) : 0; }

// ---------- the mechanism's time ----------
// beat(T): how many ticks the escapement has made (whole part) and how far the balance is through
// its swing to the next (fraction). Between two ticks more than 1.2 s apart (the silent bar) the
// balance swings out, hangs still, and falls back just in time for the next tick.
function beat(T) {
  const b = AU.beats, k = lastIdx(b, T);
  if (k < 0) return 0;
  if (k >= b.length - 1) return k + (T - b[k]) / BEAT;
  const gap = b[k + 1] - b[k]; let u = (T - b[k]) / gap;
  if (gap > 1.2) { const a = 0.35 / gap, z = 0.25 / gap; u = u < a ? 0.5 * easeOut(u / a) : u > 1 - z ? 0.5 + 0.5 * Math.pow((u - (1 - z)) / z, 2) : 0.5; }
  return k + u;
}
// the same count as the train moves: each tick a quick step with a small mechanical overshoot
function beatStep(T) {
  const b = AU.beats, k = lastIdx(b, T);
  if (k < 0) return 0;
  const x = (T - b[k]) / 0.085;
  return k + 1 - Math.exp(-3.2 * x) * Math.cos(4.2 * x);
}
const tickEnv = (T, decay = 0.12) => { const k = lastIdx(AU.beats, T); return k < 0 ? 0 : Math.exp(-(T - AU.beats[k]) / decay); };

// ---------- procedural surface finish: normal maps computed from height functions ----------
function normalMap(size, height, strength, wrap = true) {
  const h = new Float32Array(size * size);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) h[y * size + x] = height((x + 0.5) / size, (y + 0.5) / size);
  const d = new Uint8Array(size * size * 4);
  const at = (x, y) => wrap ? h[((y + size) % size) * size + ((x + size) % size)] : h[clamp(y, 0, size - 1) * size + clamp(x, 0, size - 1)];
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const dx = (at(x + 1, y) - at(x - 1, y)) * strength, dy = (at(x, y + 1) - at(x, y - 1)) * strength;
    const l = 1 / Math.hypot(dx, dy, 1), k = (y * size + x) * 4;
    d[k] = 127.5 - dx * l * 127.5; d[k + 1] = 127.5 - dy * l * 127.5; d[k + 2] = 127.5 + l * 127.5; d[k + 3] = 255;
  }
  const t = new THREE.DataTexture(d, size, size, THREE.RGBAFormat);
  t.wrapS = t.wrapT = wrap ? THREE.RepeatWrapping : THREE.ClampToEdgeWrapping;
  t.magFilter = THREE.LinearFilter; t.minFilter = THREE.LinearMipmapLinearFilter; t.generateMipmaps = true; t.anisotropy = Q.aniso ?? 2; t.needsUpdate = true;
  return t;
}
const TEX = {};
function makeTextures(serif) {
  TEX.dial = dialTexture(serif);
  TEX.engrave = engraveTexture(serif, [["ESCAPEMENT", 86, 70, 0.92], ["SEVENTEEN JEWELS  \u00b7  7,200 A/h", 34, 150, 0.8], ["adjusted to D minor", 40, 205, 0.56, "italic 500"]], 1024, 256);
  // Geneva stripes: bands with a soft scalloped profile, each crossed by fine arcs of the cutter
  TEX.stripes = normalMap(512, (u, v) => {
    const band = u * 2, f = band - Math.floor(band), i = Math.floor(band);
    const arc = Math.sin((v * 46 + Math.sqrt(Math.max(0, 1 - Math.pow(f * 2 - 1, 2))) * 5.5 * (i % 2 ? 1 : -1)) * TAU);
    return 0.9 * Math.pow(Math.sin(f * Math.PI), 0.6) + 0.045 * arc * Math.sin(f * Math.PI);
  }, 5.5);
  // perlage: overlapping circles of circular graining, each row laid over the one before
  TEX.perlage = normalMap(512, (u, v) => {
    const n = 4; let best = 0, bh = 0;
    for (let j = -1; j <= n; j++) for (let i = -1; i <= n; i++) {
      const cx = (i + (j % 2 ? 0.5 : 0) + 0.25) / n, cy = (j + 0.5) / n;
      let dx = u - cx, dy = v - cy; dx -= Math.round(dx); dy -= Math.round(dy);
      const r = Math.hypot(dx, dy) * n;
      if (r < 0.62) { const pr = ((j + 8) % n) * 10 + ((i + 8) % n) + 1; if (pr > best) { best = pr; bh = 0.35 * Math.cos(r * 60) * (0.4 + r) + 0.6 * (1 - r * r); } }
    }
    return bh;
  }, 2.6);
  // circular graining for wheels: fine concentric rings about the middle of the texture
  TEX.rings = normalMap(1024, (u, v) => { const r = Math.hypot(u - 0.5, v - 0.5); return 0.5 * Math.sin(r * 1024 * TAU / 5.5) + 0.3 * Math.sin(r * 1024 * TAU / 17.3 + 1.7); }, 0.55, false);
  // straight graining for steel
  TEX.brushed = normalMap(256, (u, v) => 0.5 * Math.sin(v * 256 * TAU / 3.1 + 2.2 * Math.sin(u * TAU)) + 0.4 * Math.sin(v * 256 * TAU / 7.3 + 1.3 * Math.sin(u * TAU * 2 + 1)), 0.5);
  // sunray: fine radial lines (ratchet and crown wheels, the dial)
  TEX.sunray = normalMap(512, (u, v) => { const a = Math.atan2(v - 0.5, u - 0.5); return 0.5 * Math.sin(a * 360) + 0.35 * Math.sin(a * 133 + 1.2) + 0.25 * Math.sin(a * 77 + 4); }, 0.6, false);
}
// the dial, drawn once: silvered, a railway minute track, Roman numerals, the name, a small seconds dial at six
function dialTexture(serif) {
  const N = 2048, c = document.createElement("canvas"); c.width = c.height = N; const g = c.getContext("2d"), k = N / 35.2, mm = (v) => v * k;
  g.translate(N / 2, N / 2);
  const bg = g.createRadialGradient(0, 0, 0, 0, 0, N / 2); bg.addColorStop(0, "#f1eee6"); bg.addColorStop(0.75, "#e9e5db"); bg.addColorStop(1, "#d9d4c8");
  g.fillStyle = bg; g.fillRect(-N / 2, -N / 2, N, N);
  const ink = "#141a2c";
  g.strokeStyle = ink; g.fillStyle = ink; g.lineCap = "butt";
  // railway track
  g.lineWidth = mm(0.07); g.beginPath(); g.arc(0, 0, mm(15.9), 0, TAU); g.stroke(); g.beginPath(); g.arc(0, 0, mm(15.0), 0, TAU); g.stroke();
  for (let i = 0; i < 60; i++) { const a = i / 60 * TAU; g.lineWidth = mm(i % 5 ? 0.07 : 0.22); g.beginPath(); g.moveTo(mm(15.0) * Math.sin(a), -mm(15.0) * Math.cos(a)); g.lineTo(mm(15.9) * Math.sin(a), -mm(15.9) * Math.cos(a)); g.stroke(); }
  // Roman numerals, each upright along its radius
  const rom = ["XII", "I", "II", "III", "IV", "V", "", "VII", "VIII", "IX", "X", "XI"];
  g.textAlign = "center"; g.textBaseline = "middle"; g.font = `600 ${mm(3.1)}px ${serif}`;
  rom.forEach((r, i) => { if (!r) return; const a = i / 12 * TAU; g.save(); g.rotate(a); g.translate(0, -mm(12.5)); g.scale(0.82, 1); g.fillText(r, 0, 0); g.restore(); });
  // the name
  g.font = `600 ${mm(1.25)}px ${serif}`; g.save(); g.translate(0, -mm(6.6));
  const name = "ESCAPEMENT", sp = mm(1.28); [...name].forEach((ch, i) => g.fillText(ch, (i - (name.length - 1) / 2) * sp, 0)); g.restore();
  g.font = `italic 500 ${mm(0.78)}px ${serif}`; g.fillText("120 beats to the minute", 0, -mm(4.9));
  // small seconds
  g.save(); g.translate(0, mm(8.3));
  const sg = g.createRadialGradient(0, 0, 0, 0, 0, mm(4.4)); sg.addColorStop(0, "#e2ded3"); sg.addColorStop(1, "#d3cec2");
  g.fillStyle = sg; g.beginPath(); g.arc(0, 0, mm(4.4), 0, TAU); g.fill();
  g.strokeStyle = "rgba(20,26,44,0.18)"; g.lineWidth = mm(0.03); for (let r = 0.25; r < 4.3; r += 0.16) { g.beginPath(); g.arc(0, 0, mm(r), 0, TAU); g.stroke(); }
  g.strokeStyle = ink; g.fillStyle = ink; g.lineWidth = mm(0.06); g.beginPath(); g.arc(0, 0, mm(4.4), 0, TAU); g.stroke(); g.beginPath(); g.arc(0, 0, mm(3.75), 0, TAU); g.stroke();
  for (let i = 0; i < 60; i++) { const a = i / 60 * TAU; g.lineWidth = mm(i % 5 ? 0.05 : 0.14); g.beginPath(); g.moveTo(mm(i % 5 ? 3.75 : 3.45) * Math.sin(a), -mm(i % 5 ? 3.75 : 3.45) * Math.cos(a)); g.lineTo(mm(4.4) * Math.sin(a), -mm(4.4) * Math.cos(a)); g.stroke(); }
  g.font = `600 ${mm(0.85)}px ${serif}`; ["60", "15", "30", "45"].forEach((t, i) => { const a = i / 4 * TAU; g.fillText(t, mm(2.65) * Math.sin(a), -mm(2.65) * Math.cos(a)); });
  g.restore();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = Q.daniso ?? 4; t.generateMipmaps = true; t.minFilter = THREE.LinearMipmapLinearFilter; return t;
}
// lettering engraved in a bridge and filled with gold: a transparent label lying on the metal
function engraveTexture(serif, lines, w, h) {
  const c = document.createElement("canvas"); c.width = w; c.height = h; const g = c.getContext("2d");
  g.textAlign = "center"; g.textBaseline = "middle"; g.fillStyle = "#fff";
  for (const [txt, size, y, spacing, style] of lines) { g.font = `${style || "600"} ${size}px ${serif}`; const sp = spacing * size; [...txt].forEach((ch, i) => g.fillText(ch, w / 2 + (i - (txt.length - 1) / 2) * sp, y)); }
  const t = new THREE.CanvasTexture(c); t.anisotropy = 4; return t;
}
const M = {};
// The key light's shadow also dims what a surface reflects of the studio: metal has no diffuse light,
// so without this a wheel would cast no visible shadow on the plate under it.
const uOcc = {value: 0.3};
function occlude(m) {
  m.onBeforeCompile = (sh) => {
    sh.uniforms.uOcc = uOcc;
    const begin = THREE.ShaderChunk.lights_fragment_begin.replace("directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( directionalShadowMap[ i ]", "directLight.color *= gSh = ( directLight.visible && receiveShadow ) ? getShadow( directionalShadowMap[ i ]");
    sh.fragmentShader = sh.fragmentShader.replace("#include <lights_fragment_begin>", "float gSh = 1.0;\n" + begin)
      .replace("#include <lights_fragment_end>", "#include <lights_fragment_end>\nreflectedLight.indirectSpecular *= mix(uOcc, 1.0, gSh); reflectedLight.indirectDiffuse *= mix(uOcc, 1.0, gSh);")
      .replace("void main() {", "uniform float uOcc;\nvoid main() {");
  };
  return m;
}
function makeMaterials() {
  const std = (o) => occlude(new THREE.MeshStandardMaterial(o));
  const rep = (t, k) => { const c = t.clone(); c.repeat.set(k, k); c.needsUpdate = true; return c; };
  M.brass = std({color: 0xd9a441, metalness: 1, roughness: 0.3, normalMap: TEX.rings, normalScale: V2(0.6, 0.6)});
  M.gold = std({color: 0xf0c060, metalness: 1, roughness: 0.2});
  M.rose = std({color: 0xe7a17c, metalness: 1, roughness: 0.22});
  M.steel = std({color: 0xcfd3d8, metalness: 1, roughness: 0.16});
  M.steelB = std({color: 0xc4c9cf, metalness: 1, roughness: 0.3, normalMap: rep(TEX.brushed, 0.5), normalScale: V2(0.35, 0.35)});
  M.sun = std({color: 0xd4d8dd, metalness: 1, roughness: 0.3, normalMap: TEX.sunray, normalScale: V2(0.8, 0.8)});
  M.plate = std({color: 0x5d5c62, metalness: 1, roughness: 0.4, normalMap: rep(TEX.perlage, 1 / 5.2), normalScale: V2(0.9, 0.9)});
  M.bridge = std({color: 0xbdbab3, metalness: 1, roughness: 0.34, normalMap: rep(TEX.stripes, 1 / 5.6), normalScale: V2(0.55, 0.55)});
  M.blued = std({color: 0x1a3fb0, metalness: 1, roughness: 0.2});
  M.bluedHand = std({color: 0x2248c0, metalness: 1, roughness: 0.22});
  M.ruby = occlude(new THREE.MeshPhysicalMaterial({color: 0xc20a2a, metalness: 0, roughness: 0.06, emissive: 0x70000c, emissiveIntensity: 0.9, clearcoat: 1, clearcoatRoughness: 0.05, ior: 1.76, reflectivity: 1}));
  if (Q.nonormal) for (const k in M) { M[k].normalMap = null; }
  M.dial = occlude(new THREE.MeshStandardMaterial({map: TEX.dial, metalness: 0.35, roughness: 0.5, transparent: true}));
  M.caseM = std({color: 0xeab08c, metalness: 1, roughness: 0.14});
  M.caseB = std({color: 0xe6ab88, metalness: 1, roughness: 0.34, normalMap: rep(TEX.brushed, 0.35), normalScale: V2(0.4, 0.4)});
  M.leather = std({color: 0x17100c, metalness: 0, roughness: 0.75});
  M.glass = new THREE.MeshStandardMaterial({color: 0x0e1012, metalness: 1, roughness: 0.02, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false});
  M.engrave = occlude(new THREE.MeshStandardMaterial({color: 0xf2c25a, metalness: 1, roughness: 0.25, alphaMap: TEX.engrave, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2}));
  M.dark = std({color: 0x0a0a0c, metalness: 0.3, roughness: 0.6});
}

// ---------- the studio: soft boxes on a dark dome, baked through PMREM into the environment ----------
const ENV_FRAG = /* glsl */`
varying vec3 vDir;
uniform vec3 uL[8]; uniform vec3 uU[8]; uniform vec4 uS[8]; uniform vec3 uC[8]; uniform vec3 uSky, uFloor; uniform int uN;
void main(){
  vec3 d = normalize(vDir);
  vec3 col = mix(uFloor, uSky, smoothstep(-0.3, 0.6, d.z));
  for (int i = 0; i < 8; i++) { if (i >= uN) break;
    vec3 L = uL[i]; float dl = dot(d, L);
    if (dl > 0.05) { vec3 U = uU[i], V = cross(L, U); vec2 p = vec2(dot(d, U), dot(d, V)) / dl;
      float sx = uS[i].z, m = (1.0 - smoothstep(uS[i].x - sx, uS[i].x + sx, abs(p.x))) * (1.0 - smoothstep(uS[i].y - sx, uS[i].y + sx, abs(p.y)));
      col += uC[i] * m * (1.0 + uS[i].w * p.x); }
  }
  gl_FragColor = vec4(col, 1.0);
}`;
// lights: [direction, "up" hint, half-width, half-height, softness, gradient, colour, intensity]
function makeEnv(lights, sky, floor, blur = 0.02) {
  const u = {uL: {value: []}, uU: {value: []}, uS: {value: []}, uC: {value: []}, uSky: {value: sky}, uFloor: {value: floor}, uN: {value: lights.length}};
  for (let i = 0; i < 8; i++) {
    const l = lights[i] || [[0, 0, 1], [1, 0, 0], 0, 0, 0.1, 0, 0x000000, 0];
    const L = new THREE.Vector3(...l[0]).normalize(), U = new THREE.Vector3(...l[1]); U.addScaledVector(L, -U.dot(L)).normalize();
    u.uL.value.push(L); u.uU.value.push(U); u.uS.value.push(new THREE.Vector4(l[2], l[3], l[4], l[5])); u.uC.value.push(hx(l[6], l[7]));
  }
  const sc = new THREE.Scene();
  sc.add(new THREE.Mesh(new THREE.SphereGeometry(50, 48, 24), new THREE.ShaderMaterial({uniforms: u, side: THREE.BackSide,
    vertexShader: "varying vec3 vDir; void main(){ vDir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }", fragmentShader: ENV_FRAG})));
  const rt = PM.fromScene(sc, blur, 1, 200);
  return rt.texture;
}
const STUDIO = {
  // a big soft warm box off to one side (flat plates catch its falling edge, not its middle), a cool strip,
  // a long warm rim below, a cool rim above, and two small hard lights for sparkle
  warm: () => makeEnv([
    [[-0.5, 0.62, 0.6], [1, 0, 0], 0.5, 0.36, 0.42, 0.3, 0xfff0dc, 1.25],
    [[0.86, -0.15, 0.48], [0, 1, 0], 0.13, 0.9, 0.06, 0, 0xcfe2ff, 1.5],
    [[-0.2, -0.92, 0.33], [1, 0, 0], 1.1, 0.1, 0.06, 0, 0xffd9b0, 0.9],
    [[0.3, 0.93, 0.2], [1, 0, 0], 0.8, 0.09, 0.05, 0, 0xbcd4ff, 1.1],
    [[-0.88, 0.1, 0.46], [0, 1, 0], 0.045, 0.045, 0.02, 0, 0xffffff, 18],
    [[0.5, 0.42, 0.76], [1, 0, 0], 0.03, 0.03, 0.015, 0, 0xfff2dd, 26],
    [[0.1, -0.1, 1], [1, 0, 0], 0.9, 0.9, 0.8, 0.5, 0xfff4e6, 0.34],
  ], hx(0x101216, 1), hx(0x0a0806, 1)),
  cool: () => makeEnv([
    [[-0.5, 0.62, 0.6], [1, 0, 0], 0.5, 0.36, 0.42, 0.3, 0xdde9ff, 1.2],
    [[0.86, -0.15, 0.48], [0, 1, 0], 0.12, 0.9, 0.06, 0, 0x9fc0ff, 1.3],
    [[-0.2, -0.92, 0.33], [1, 0, 0], 1.1, 0.09, 0.06, 0, 0xffc890, 0.7],
    [[0.5, 0.42, 0.76], [1, 0, 0], 0.03, 0.03, 0.015, 0, 0xffffff, 22],
    [[0.1, -0.1, 1], [1, 0, 0], 0.9, 0.9, 0.8, 0.5, 0xe6f0ff, 0.3],
  ], hx(0x0a0d14, 1), hx(0x050608, 1)),
};

// ---------- geometry ----------
const extrude = (shape, depth, bevel = 0.03, z = 0) => {
  const g = new THREE.ExtrudeGeometry(shape, {depth: depth - 2 * bevel, bevelEnabled: bevel > 0, bevelThickness: bevel, bevelSize: bevel, bevelOffset: -bevel, bevelSegments: 1, curveSegments: 24, steps: 1});
  g.translate(0, 0, z + bevel); return g;
};
// planar texture coordinates in millimetres about the part's own centre (for ring and sunray maps)
function centreUV(g, span) { const p = g.attributes.position, uv = g.attributes.uv; for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i) / span + 0.5, p.getY(i) / span + 0.5); return g; }
function planarUV(g) { const p = g.attributes.position, uv = g.attributes.uv; for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i), p.getY(i)); return g; }
// The outline of a watch wheel or pinion: N teeth of module m (pitch radius N m / 2), a tooth centred on angle 0.
// Wheels have slender ogival teeth (the cycloidal form of watchmaking), pinions rounder leaves.
function toothOutline(N, m, o = {}) {
  const rp = N * m / 2, pin = o.pinion ?? N < 20, add = (pin ? 0.95 : 1.25) * m, ded = (pin ? 1.25 : 1.4) * m;
  const ra = rp + add, rr = rp - ded, pitch = TAU / N, hw = pitch * 0.25 * (pin ? 0.84 : 0.9);
  const prof = pin ? [[rr, 1.12], [rp - ded * 0.4, 1.02], [rp, 1], [rp + add * 0.4, 0.9], [rp + add * 0.75, 0.62], [ra, 0.22]]
    : [[rr, 1.1], [rp - ded * 0.45, 1.0], [rp, 1], [rp + add * 0.35, 0.9], [rp + add * 0.68, 0.64], [rp + add * 0.9, 0.36], [ra, 0.1]];
  const pts = [];
  for (let i = 0; i < N; i++) {
    const c = i * pitch;
    for (let k = 0; k < prof.length; k++) pts.push(pol(prof[k][0], c - hw * prof[k][1]));
    for (let k = prof.length - 1; k >= 0; k--) pts.push(pol(prof[k][0], c + hw * prof[k][1]));
    pts.push(pol(rr - 0.04 * m, c + pitch / 2));
  }
  return {pts, rp, ra, rr};
}
// a wheel: toothed rim, spokes (crossings) and hub, cut from one plate
function wheelGeo(N, m, t, o = {}) {
  const {pts, rr, rp} = toothOutline(N, m, {pinion: false});
  const sh = new THREE.Shape(pts);
  const ri = rr - (o.rim ?? Math.max(0.28, rp * 0.085)), rh = o.hub ?? Math.max(0.42, rp * 0.2), n = o.spokes ?? 5, w = o.spokeW ?? Math.max(0.2, rp * 0.085);
  if (n > 0) for (let k = 0; k < n; k++) {
    const c0 = k * TAU / n + (o.spokeRot ?? 0), c1 = c0 + TAU / n;
    const ai = Math.asin(w / 2 / ri) + 0.02, ah = Math.asin(Math.min(0.99, w / 2 / rh)) + 0.02;
    const h = [...arcPts(ri, c0 + ai, c1 - ai, 14), ...arcPts(rh, c1 - ah, c0 + ah, 6)];
    sh.holes.push(new THREE.Path(h));
  }
  if (o.bore) sh.holes.push(new THREE.Path(arcPts(o.bore, 0, TAU, 12).slice(0, -1)));
  return centreUV(extrude(sh, t, o.bevel ?? 0.035), 13);
}
function pinionGeo(N, m, len) {
  const {pts} = toothOutline(N, m, {pinion: true});
  return extrude(new THREE.Shape(pts), len, 0.02);
}
// the club-toothed escape wheel of a Swiss lever escapement
function escapeWheelGeo(N, Rt, t) {
  const pts = [], pitch = TAU / N, rb = Rt * 0.74;
  for (let i = 0; i < N; i++) {
    const c = i * pitch;                                    // the wheel turns clockwise (towards negative angles): the club leads
    pts.push(pol(rb, c + pitch * 0.46), pol(rb, c + pitch * 0.24), pol(Rt * 0.955, c - pitch * 0.045), pol(Rt, c - pitch * 0.02), pol(Rt, c - pitch * 0.2), pol(Rt * 0.9, c - pitch * 0.2), pol(rb * 1.02, c - pitch * 0.06));
  }
  const sh = new THREE.Shape(pts), ri = rb - 0.2, rh = 0.42, n = 4, w = 0.16;
  for (let k = 0; k < n; k++) {
    const c0 = k * TAU / n, c1 = c0 + TAU / n, ai = Math.asin(w / 2 / ri) + 0.03, ah = Math.asin(w / 2 / rh) + 0.03;
    sh.holes.push(new THREE.Path([...arcPts(ri, c0 + ai, c1 - ai, 12), ...arcPts(rh, c1 - ah, c0 + ah, 5)]));
  }
  return extrude(sh, t, 0.02);
}
const cyl = (r, z0, z1, seg = 24, r2 = r) => { const g = new THREE.CylinderGeometry(r2, r, z1 - z0, seg); g.rotateX(Math.PI / 2); g.translate(0, 0, (z0 + z1) / 2); return g; };
// a turned part: a profile of [radius, z] spun about the z axis
const lathe = (prof, seg = 48) => { const g = new THREE.LatheGeometry(prof.map((p) => V2(p[0], p[1])), seg); g.rotateX(Math.PI / 2); return g; };
// a screw head: chamfered, polished, with a slot
function screwGeo(r, h) {
  const b = arcPts(r, 0, TAU, 20).slice(0, -1), s = r * 0.16;
  const half = (sgn) => { const a = Math.asin(s / r), p = arcPts(r, sgn > 0 ? a : Math.PI + a, sgn > 0 ? Math.PI - a : TAU - a, 12); return extrude(new THREE.Shape(p), h * 0.5, r * 0.1, h * 0.5); };
  return BGU.mergeGeometries([extrude(new THREE.Shape(b), h * 0.5, 0, 0), half(1), half(-1)]);
}
// a jewel in its gold chaton: a ring of gold, a domed ruby with an oil sink
function jewelParts(rj) {
  const chaton = lathe([[rj * 1.05, 0], [rj * 1.75, 0], [rj * 1.75, 0.07], [rj * 1.6, 0.11], [rj * 1.08, 0.11], [rj * 1.05, 0.06]], 28);
  const ruby = lathe([[0.001, 0.05], [rj * 0.3, 0.05], [rj * 0.5, 0.1], [rj * 0.95, 0.13], [rj * 1.06, 0.1], [rj * 1.06, 0]], 24);
  return {chaton, ruby};
}
function capsuleShape(p0, r0, p1, r1, n = 14) {
  const a = Math.atan2(p1.y - p0.y, p1.x - p0.x), d = Math.hypot(p1.x - p0.x, p1.y - p0.y), b = Math.acos(clamp((r0 - r1) / d, -1, 1));
  return new THREE.Shape([...arcPts(r0, a + b, a + TAU - b, n * 2, p0.x, p0.y), ...arcPts(r1, a - b, a + b, n, p1.x, p1.y)]);
}
// a finger bridge: a slender waisted bar along a gently bent centre line, round at both ends
function fingerShape(p0, r0, p1, r1, waist, bend, n = 22) {
  const dx = p1.x - p0.x, dy = p1.y - p0.y, len = Math.hypot(dx, dy), nx = -dy / len, ny = dx / len;
  const cx = (p0.x + p1.x) / 2 + nx * bend, cy = (p0.y + p1.y) / 2 + ny * bend, L = [], Rr = [];
  let a0 = 0, a1 = 0;
  for (let i = 0; i <= n; i++) {
    const u = i / n, x = (1 - u) * (1 - u) * p0.x + 2 * u * (1 - u) * cx + u * u * p1.x, y = (1 - u) * (1 - u) * p0.y + 2 * u * (1 - u) * cy + u * u * p1.y;
    let tx = 2 * (1 - u) * (cx - p0.x) + 2 * u * (p1.x - cx), ty = 2 * (1 - u) * (cy - p0.y) + 2 * u * (p1.y - cy); const tl = Math.hypot(tx, ty); tx /= tl; ty /= tl;
    const base = mix(r0, r1, u), w = base - (base - waist) * Math.pow(Math.sin(Math.PI * u), 0.7);
    L.push(V2(x - ty * w, y + tx * w)); Rr.push(V2(x + ty * w, y - tx * w));
    if (i === 0) a0 = Math.atan2(ty, tx); if (i === n) a1 = Math.atan2(ty, tx);
  }
  return new THREE.Shape([...L, ...arcPts(r1, a1 + Math.PI / 2, a1 - Math.PI / 2, 12, p1.x, p1.y).slice(1, -1), ...Rr.reverse(), ...arcPts(r0, a0 - Math.PI / 2, a0 - 3 * Math.PI / 2, 14, p0.x, p0.y).slice(1, -1)]);
}
// the angle of gear b (Nb teeth) in mesh with gear a (Na teeth, at angle ta), b lying in direction phi from a
const meshAngle = (ta, Na, Nb, phi) => phi + Math.PI - Math.PI / Nb + (phi - ta) * Na / Nb;

// ---------- the calibre ----------
const CAL = (() => {
  const c = {};
  c.Nbarrel = 72; c.NcP = 9; c.mB = 0.22;
  c.Nc = 64; c.N3P = 8; c.mC = 0.16;
  c.N3 = 60; c.N4P = 8; c.m3 = 0.13;
  c.N4 = 48; c.NeP = 12; c.m4 = 0.11;
  c.Ne = 15; c.Re = 2.2;
  c.centre = V2(0, 0);
  c.fourth = V2(0, -8.3);
  const d3 = (c.Nc + c.N3P) * c.mC / 2, d4 = (c.N3 + c.N4P) * c.m3 / 2;      // third: in mesh with both the centre and the fourth
  const y3 = (d4 * d4 - d3 * d3 - 8.3 * 8.3) / (2 * 8.3);
  c.third = V2(Math.sqrt(d3 * d3 - y3 * y3), y3);
  c.barrel = pol((c.Nbarrel + c.NcP) * c.mB / 2, 65 * DEG);
  c.escape = c.fourth.clone().add(pol((c.N4 + c.NeP) * c.m4 / 2, 160 * DEG));
  c.lineA = 125 * DEG;                                                        // escape wheel, pallets and balance on one line
  c.palletD = c.Re / Math.cos(30 * DEG);
  c.pallet = c.escape.clone().add(pol(c.palletD, c.lineA));
  c.forkL = 2.9; c.rollerR = 0.55;
  c.balance = c.pallet.clone().add(pol(c.forkL + c.rollerR, c.lineA));
  c.balR = 5.2;
  c.Nr = 36; c.Ncw = 24; c.mR = 0.2;                                            // ratchet wheel (on the barrel arbor) and crown wheel
  c.crownW = c.barrel.clone().add(pol((c.Nr + c.Ncw) * c.mR / 2, -62 * DEG));
  c.R = 17.6;
  c.NpA = 36; c.NpB = 48; c.mP = 0.13;                                         // three against four: 36 and 48 teeth, 12 teeth a bar
  c.polyA = V2(11.2, -5.2); c.polyB = c.polyA.clone().add(pol((c.NpA + c.NpB) * c.mP / 2, -115 * DEG));
  c.gongR = 16.75;
  // heights above the main plate (mm)
  c.z = {barrel: 0.25, L2: 1.0, L3: 1.78, bridge: 2.55, top: 3.15, bal: 2.95, cock: 4.0, dial: 5.1, hands: 5.5};
  return c;
})();

// The watch. Returns {root, layers, update(T, opts)}; opts: explode (0..1), dial (0..1 opacity), run (amplitude 0..1).
function buildWatch(o = {}) {
  const root = new THREE.Group(), L = {}, Z = CAL.z;
  const layerNames = ["plate", "barrel", "l2", "l3", "poly", "lowbridge", "bridge", "wind", "balance", "cock", "dial", "hands", "glass", "case"];
  for (const n of layerNames) { L[n] = new THREE.Group(); root.add(L[n]); }
  const mesh = (g, m, layer, x = 0, y = 0) => { const q = new THREE.Mesh(g, m); q.position.set(x, y, 0); q.castShadow = q.receiveShadow = true; (layer.isObject3D ? layer : L[layer]).add(q); return q; };
  const arbor = (p, layer) => { const g = new THREE.Group(); g.position.set(p.x, p.y, 0); L[layer].add(g); return g; };
  const A = {};
  const jewel = jewelParts(0.36), jewelS = jewelParts(0.26);
  const screwG = screwGeo(0.52, 0.3), screwS = screwGeo(0.36, 0.24);
  let nS = 0;
  const screw = (layer, x, y, z, small = false) => { const q = mesh(small ? screwS : screwG, M.blued, layer, x, y); q.position.z = z; q.rotation.z = hash1(++nS, 3) * Math.PI; return q; };
  const setJewel = (layer, p, z, small = false) => { const j = small ? jewelS : jewel; const a = mesh(j.chaton, M.gold, layer, p.x, p.y), b = mesh(j.ruby, M.ruby, layer, p.x, p.y); a.position.z = b.position.z = z; return b; };

  // --- main plate: perlage, a polished bevelled edge
  mesh(planarUV(extrude(new THREE.Shape(arcPts(CAL.R, 0, TAU, 96).slice(0, -1)), 1.0, 0.08, -1.0)), M.plate, "plate");
  for (const p of [CAL.centre, CAL.third, CAL.fourth, CAL.escape, CAL.pallet, CAL.balance]) setJewel("plate", p, 0, p !== CAL.centre);

  // --- barrel (mainspring) with its teeth, and the centre pinion it drives
  A.barrel = arbor(CAL.barrel, "barrel");
  { const {pts, rr} = toothOutline(CAL.Nbarrel, CAL.mB, {pinion: false});
    mesh(centreUV(extrude(new THREE.Shape(pts), 0.34, 0.03, Z.barrel), 13), M.brass, A.barrel);
    mesh(centreUV(lathe([[0.5, Z.barrel + 0.3], [rr - 0.25, Z.barrel + 0.3], [rr - 0.2, Z.barrel + 0.36], [rr - 0.2, Z.barrel + 1.5], [rr - 0.3, Z.barrel + 1.62], [1.2, Z.barrel + 1.62], [1.2, Z.barrel + 1.75], [0.5, Z.barrel + 1.75]], 72), 13), M.brass, A.barrel);
    mesh(cyl(0.5, 0, Z.top + 0.2), M.steel, A.barrel); }

  // --- the going train
  const trainWheel = (name, p, layer, N, m, zw, spokes, pinN, pinM, zp0, zp1, zTop) => {
    const a = A[name] = arbor(p, layer);
    if (N) mesh(wheelGeo(N, m, 0.2, {spokes}), M.brass, a).position.z = zw;
    if (pinN) mesh(pinionGeo(pinN, pinM, zp1 - zp0), M.steel, a).position.z = zp0;
    mesh(cyl(0.2, 0.05, zTop, 12), M.steel, a);
    mesh(cyl(0.34, zw - 0.12, zw + 0.34, 16), M.steel, a);
    return a;
  };
  trainWheel("centre", CAL.centre, "l2", CAL.Nc, CAL.mC, Z.L2, 5, CAL.NcP, CAL.mB, Z.barrel - 0.05, Z.barrel + 0.5, Z.hands + 0.3);
  trainWheel("third", CAL.third, "l3", CAL.N3, CAL.m3, Z.L3, 5, CAL.N3P, CAL.mC, Z.L2 - 0.15, Z.L2 + 0.4, Z.bridge);
  trainWheel("fourth", CAL.fourth, "l2", CAL.N4, CAL.m4, Z.L2, 4, CAL.N4P, CAL.m3, Z.L3 - 0.15, Z.L3 + 0.4, Z.hands + 0.1);
  A.escape = arbor(CAL.escape, "l3");
  mesh(escapeWheelGeo(CAL.Ne, CAL.Re, 0.13), M.steel, A.escape).position.z = Z.L3;
  mesh(pinionGeo(CAL.NeP, CAL.m4, 0.5), M.steel, A.escape).position.z = Z.L2 - 0.15;
  mesh(cyl(0.14, 0.05, Z.bridge - 0.2, 12), M.steel, A.escape);

  // --- the lever: pallet fork with its two ruby pallets, turning about its own arbor
  A.pallet = arbor(CAL.pallet, "l3");
  { const Lf = CAL.forkL - 0.02, d = CAL.palletD, Rr = CAL.Re, sx = -d + Rr * Math.cos(30 * DEG), sy = Rr * Math.sin(30 * DEG);
    const sh = new THREE.Shape([V2(Lf + 0.42, 0.34), V2(Lf + 0.42, 0.12), V2(Lf + 0.02, 0.12), V2(Lf + 0.02, -0.12), V2(Lf + 0.42, -0.12), V2(Lf + 0.42, -0.34), V2(Lf - 0.25, -0.2), V2(0.55, -0.24),
      V2(0.05, -0.5), V2(sx + 0.42, -sy - 0.12), V2(sx + 0.2, -sy - 0.3), V2(sx - 0.26, -sy - 0.22), V2(sx - 0.3, -sy + 0.22), V2(sx - 0.02, -sy + 0.32), V2(-0.42, -0.3), V2(-0.52, 0),
      V2(-0.42, 0.3), V2(sx - 0.02, sy - 0.32), V2(sx - 0.3, sy - 0.22), V2(sx - 0.26, sy + 0.22), V2(sx + 0.2, sy + 0.3), V2(sx + 0.42, sy + 0.12), V2(0.05, 0.5), V2(0.55, 0.24), V2(Lf - 0.25, 0.2)]);
    const g = new THREE.Group(); g.rotation.z = CAL.lineA; A.pallet.add(g); A.fork = g;
    mesh(extrude(sh, 0.13, 0.025, Z.L3), M.steel, g);
    for (const s of [1, -1]) { const st = mesh(new THREE.BoxGeometry(0.62, 0.2, 0.2), M.ruby, g, sx - 0.2, s * sy); st.position.z = Z.L3 + 0.065; st.rotation.z = s * -22 * DEG; }
    mesh(cyl(0.12, 0.05, Z.bridge - 0.25, 12), M.steel, A.pallet); mesh(cyl(0.26, Z.L3 - 0.06, Z.L3 + 0.2, 16), M.steel, A.pallet); }

  // --- the balance: rim with timing screws, two arms, roller with its ruby pin, the breathing hairspring
  A.balance = arbor(CAL.balance, "balance");
  { const Rb = CAL.balR, ri = Rb - 0.55, w = 0.56, rh = 0.7, zb = Z.bal;
    const rim = new THREE.Shape(arcPts(Rb, 0, TAU, 96).slice(0, -1)); rim.holes.push(new THREE.Path(arcPts(ri, 0, TAU, 80).slice(0, -1)));
    mesh(extrude(rim, 0.3, 0.05, zb), M.gold, A.balance);
    mesh(extrude(new THREE.Shape(arcPts(rh, 0, TAU, 28).slice(0, -1)), 0.3, 0.05, zb), M.gold, A.balance);
    // The arms and the timing screws move up to 54 degrees a frame as the balance passes its centre. They are drawn
    // six times across the time the shutter is open, each copy partly transparent: motion blur for these parts only.
    const armSh = (sg) => new THREE.Shape([V2(sg * (rh - 0.08), -w / 2), V2(sg * (ri + 0.08), -w / 2), V2(sg * (ri + 0.08), w / 2), V2(sg * (rh - 0.08), w / 2)]);
    const armG = BGU.mergeGeometries([extrude(armSh(1), 0.26, 0.04, zb + 0.02), extrude(armSh(-1), 0.26, 0.04, zb + 0.02)]);
    const scr = [];
    for (let i = 0; i < 18; i++) { const a = (i + 0.5) / 18 * TAU, g = cyl(0.18, 0, 0.3, 10); g.rotateY(Math.PI / 2); g.rotateZ(a); g.translate(Math.cos(a) * (Rb - 0.04), Math.sin(a) * (Rb - 0.04), zb + 0.15); scr.push(g); }
    const scrG = BGU.mergeGeometries(scr);
    const ghost = () => occlude(new THREE.MeshStandardMaterial({color: 0xf0c060, metalness: 1, roughness: 0.2, transparent: true, depthWrite: false}));
    A.spin = {arm: ghost(), scr: ghost(), g: []};
    for (let k = 0; k < 6; k++) { const g = new THREE.Group(); g.position.set(CAL.balance.x, CAL.balance.y, 0); L.balance.add(g);
      const m1 = new THREE.Mesh(armG, A.spin.arm), m2 = new THREE.Mesh(scrG, A.spin.scr); m1.receiveShadow = m2.receiveShadow = true; m1.renderOrder = m2.renderOrder = 4; g.add(m1, m2); A.spin.g.push(g); }
    mesh(cyl(0.13, 0.05, Z.cock + 0.05, 12), M.steel, A.balance);
    mesh(cyl(0.72, Z.L3 + 0.2, Z.L3 + 0.3, 28), M.steel, A.balance);                         // roller table
    const pin = mesh(cyl(0.085, Z.L3 - 0.05, Z.L3 + 0.2, 10), M.ruby, A.balance); pin.geometry.translate(0, 0, 0);
    A.rollerPin = pin;
    mesh(cyl(0.34, zb + 0.3, zb + 0.75, 20), M.gold, A.balance);                              // collet
    // hairspring: a ribbon of blued steel, rebuilt each frame as the balance winds and unwinds it
    const rings = 12 * 40 + 1, pos = new Float32Array(rings * 4 * 3), idx = [];
    for (let i = 0; i < rings - 1; i++) for (let k = 0; k < 4; k++) { const a = i * 4 + k, b = i * 4 + (k + 1) % 4, c = a + 4, d = b + 4; idx.push(a, c, b, b, c, d); }
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setIndex(idx);
    const hs = new THREE.Mesh(g, occlude(new THREE.MeshStandardMaterial({color: 0x2a4fd0, metalness: 1, roughness: 0.25, flatShading: true}))); hs.frustumCulled = false; hs.castShadow = true;
    L.balance.add(hs); hs.position.set(CAL.balance.x, CAL.balance.y, 0);
    A.hair = {mesh: hs, pos, rings, z: zb + 0.52}; }

  // --- bridges: slender fingers from the edge of the plate to each jewel, Geneva stripes, blued screws
  const finger = (p, ang, z, bend, layer = "bridge", small = false) => {
    const anchor = pol(CAL.R - 1.75, ang * DEG);
    mesh(planarUV(extrude(fingerShape(anchor, small ? 1.05 : 1.25, p, small ? 0.72 : 0.92, small ? 0.36 : 0.46, bend), 0.42, 0.07, z)), M.bridge, layer);
    screw(layer, anchor.x, anchor.y, z + 0.42, small);
    return setJewel(layer, p, z + 0.42, small);
  };
  const J = [];
  J.push(finger(CAL.third, -62, Z.bridge, -0.7));
  J.push(finger(CAL.fourth, -88, Z.bridge, 0.5));
  J.push(finger(CAL.escape, -128, Z.bridge - 0.35, 0.6, "lowbridge", true));
  { // the pallet bridge: a small bar across the lever's arbor
    const t = pol(1, CAL.lineA + Math.PI / 2), a = CAL.pallet.clone().addScaledVector(t, 2.1), b = CAL.pallet.clone().addScaledVector(t, -2.1);
    mesh(planarUV(extrude(capsuleShape(a, 0.55, b, 0.55), 0.3, 0.05, Z.bridge - 0.42)), M.bridge, "lowbridge");
    screw("lowbridge", a.x, a.y, Z.bridge - 0.12, true); screw("lowbridge", b.x, b.y, Z.bridge - 0.12, true);
    J.push(setJewel("lowbridge", CAL.pallet, Z.bridge - 0.12, true)); }
  { // the balance cock, with its regulator
    const anchor = pol(CAL.R - 1.7, 178 * DEG);
    mesh(planarUV(extrude(fingerShape(anchor, 1.5, CAL.balance, 1.1, 0.7, 0.8), 0.45, 0.08, Z.cock)), M.bridge, "cock");
    screw("cock", anchor.x, anchor.y, Z.cock + 0.45);
    J.push(setJewel("cock", CAL.balance, Z.cock + 0.45));
    const reg = new THREE.Shape([...arcPts(0.8, 0.5, TAU - 0.5, 20), V2(3.9, -0.12), V2(4.15, 0), V2(3.9, 0.12)]);
    reg.holes.push(new THREE.Path(arcPts(0.56, 0, TAU, 16).slice(0, -1)));
    const r = mesh(extrude(reg, 0.12, 0.02, Z.cock + 0.46), M.steel, "cock", CAL.balance.x, CAL.balance.y); r.rotation.z = 205 * DEG;
    const stud = mesh(cyl(0.2, Z.bal + 0.45, Z.cock, 10), M.steel, "cock", CAL.balance.x + 3.5 * Math.cos(1.0), CAL.balance.y + 3.5 * Math.sin(1.0)); }
  { // the barrel bridge: a broad plate over the mainspring, carrying the winding wheels and the engraving
    const sh = new THREE.Shape();
    const a0 = 3 * DEG, a1 = 154 * DEG, Ro = CAL.R - 0.55;
    sh.moveTo(Ro * Math.cos(a0), Ro * Math.sin(a0)); sh.absarc(0, 0, Ro, a0, a1, false);
    sh.bezierCurveTo(-10.5, 6.6, -7.0, 8.4, -4.2, 6.9); sh.bezierCurveTo(-2.4, 6.0, -1.7, 3.0, -1.3, 0); sh.bezierCurveTo(-1.25, -1.75, 1.25, -1.75, 1.3, 0); sh.bezierCurveTo(1.6, 2.4, 2.6, 2.3, 4.0, 1.5); sh.bezierCurveTo(4.9, 1.0, 5.4, -0.1, 6.5, -0.3); sh.bezierCurveTo(10.0, -1.0, 13.0, 0.9, Ro * Math.cos(a0), Ro * Math.sin(a0));
    mesh(planarUV(extrude(sh, 0.5, 0.08, Z.bridge)), M.bridge, "bridge");
    J.push(setJewel("bridge", CAL.centre, Z.bridge + 0.5));
    for (const [r, a] of [[15.3, 12], [15.3, 147], [15.5, 62], [15.5, 104], [6.9, 128]]) { const p = pol(r, a * DEG); screw("bridge", p.x, p.y, Z.bridge + 0.5); }
    // ratchet wheel and crown wheel: steel, sunray finished, with wolf-ish teeth
    A.ratchet = arbor(CAL.barrel, "wind"); A.crownW = arbor(CAL.crownW, "wind");
    const wg = (N) => { const {pts} = toothOutline(N, CAL.mR, {pinion: true}); const s = new THREE.Shape(pts); return centreUV(extrude(s, 0.28, 0.04, Z.bridge + 0.56), 13); };
    mesh(wg(CAL.Nr), M.sun, A.ratchet); mesh(wg(CAL.Ncw), M.sun, A.crownW);
    mesh(screwGeo(0.85, 0.3), M.blued, A.ratchet).position.z = Z.bridge + 0.84;
    mesh(screwGeo(0.7, 0.28), M.blued, A.crownW).position.z = Z.bridge + 0.84;
    // the click: a pawl sprung against the ratchet wheel
    const cp = CAL.barrel.clone().add(pol(CAL.Nr * CAL.mR / 2 + 1.25, 150 * DEG));
    A.click = arbor(cp, "wind");
    const cs = new THREE.Shape([...arcPts(0.5, 0.6, TAU - 0.6, 14), V2(1.5, -0.2), V2(1.72, 0.02), V2(1.45, 0.16)]);
    mesh(extrude(cs, 0.2, 0.03, Z.bridge + 0.56), M.steel, A.click); screw("wind", cp.x, cp.y, Z.bridge + 0.76, true);
    A.clickBase = Math.atan2(CAL.barrel.y - cp.y, CAL.barrel.x - cp.x) + 0.2; }

  // --- the winding stem, from the crown wheel out to the crown
  { const g = cyl(0.42, 9.2, CAL.R + 3.2, 14); g.rotateY(Math.PI / 2); g.rotateX(Math.PI / 2);
    A.stem = new THREE.Group(); A.stem.position.set(0, 0.35, 0); L.plate.add(A.stem);
    const st = new THREE.Mesh(g, M.steel); st.position.z = 0; A.stem.add(st); A.stem.position.z = 0.75; }

  // --- three against four: two wheels in mesh, 36 and 48 teeth, with pins that lift two hammers; a third hammer strikes the hours
  const H = {};
  { A.polyA = arbor(CAL.polyA, "poly"); A.polyB = arbor(CAL.polyB, "poly");
    const zw = Z.L2 - 0.05;
    const pw = (a, N, spokes, pins, p) => {
      mesh(wheelGeo(N, CAL.mP, 0.2, {spokes, hub: 0.6}), M.rose, a).position.z = zw;
      const rp = N * CAL.mP / 2 - 0.62, gs = []; for (let i = 0; i < pins; i++) { const g = cyl(0.1, zw + 0.18, zw + 0.5, 8); g.translate(rp * Math.cos(i * TAU / pins), rp * Math.sin(i * TAU / pins), 0); gs.push(g); }
      mesh(BGU.mergeGeometries(gs), M.steel, a); mesh(cyl(0.2, 0.05, zw + 0.3, 12), M.steel, a);
      const sc = mesh(screwS, M.blued, a); sc.position.z = zw + 0.22; setJewel("plate", p, 0, true); return rp;
    };
    A.pinRA = pw(A.polyA, CAL.NpA, 3, 9, CAL.polyA); A.pinRB = pw(A.polyB, CAL.NpB, 4, 16, CAL.polyB);
    const gong = (a0, a1) => { const g = new THREE.TorusGeometry(CAL.gongR, 0.16, 8, 64, (a1 - a0) * DEG); g.rotateZ(a0 * DEG); g.translate(0, 0, zw + 0.55); mesh(g, M.blued, "poly");
      const f = pol(CAL.gongR, a0 * DEG); mesh(cyl(0.5, 0, zw + 0.8, 14), M.steel, "poly", f.x, f.y); screw("poly", f.x, f.y, zw + 0.8, true); };
    gong(-55, -6); gong(190, 225);
    // a bell-crank hammer: its tail is lifted by the pins, its head falls on the gong
    const lever = (name, ang, tailTo, sgn, big = 1) => {
      const hl = 2.4 * big, piv = pol(CAL.gongR - 0.16 - 0.3 - 0.8 * big, ang * DEG), g = arbor(piv, "poly"), rad = ang * DEG;
      const tx = -Math.sin(rad) * sgn, ty = Math.cos(rad) * sgn, oy = -sgn, dx = tailTo.x - piv.x, dy = tailTo.y - piv.y, lx = dx * tx + dy * ty, ly = -dx * ty + dy * tx;
      const geo = BGU.mergeGeometries([extrude(capsuleShape(V2(0, 0), 0.46 * big, V2(hl, 0), 0.3 * big), 0.2, 0.03, zw + 0.42), extrude(new THREE.Shape(arcPts(0.5 * big, 0, TAU, 20, hl, oy * 0.3 * big).slice(0, -1)), 0.36, 0.05, zw + 0.36),
        extrude(capsuleShape(V2(0, 0), 0.46 * big, V2(lx, ly), 0.15), 0.2, 0.03, zw + 0.42)]);
      const inner = new THREE.Group(); g.add(inner); mesh(geo, M.steel, inner); screw("poly", piv.x, piv.y, zw + 0.62, true);
      H[name] = {g: inner, base: Math.atan2(ty, tx), out: oy, strike: 0.3 / hl, hit: new THREE.Vector3(piv.x + tx * hl + Math.cos(rad) * 0.8 * big, piv.y + ty * hl + Math.sin(rad) * 0.8 * big, zw + 0.6)};
      return piv;
    };
    const pA = lever("three", -14, CAL.polyA.clone().add(pol(A.pinRA, 0.4)), 1), pB = lever("four", -36, CAL.polyB.clone().add(pol(A.pinRB, 0.85)), -1);
    lever("chime", 207, V2(-9.5, -8.6), 1, 1.35);
    A.pinAngA = Math.atan2(pA.y - CAL.polyA.y, pA.x - CAL.polyA.x); }
  // the times the four-side hammer strikes: the beats, in the bars where the three plays against them
  const fourT = Float64Array.from(AU.beats.filter((b) => (b >= 80 - 1e-6 && b < 96) || (b >= 120 - 1e-6 && b <= 134.01)));
  const hammer = (h, ts, T) => {
    const i = lastIdx(ts, T), tp = i < 0 ? 9 : T - ts[i], tn = i + 1 < ts.length ? ts[i + 1] - T : 9;
    const lift = tn < 0.42 ? Math.pow((0.42 - tn) / 0.42, 1.6) : 0;
    h.g.rotation.z = h.base + h.out * (-0.3 * lift + h.strike * Math.exp(-tp / 0.03));
    return Math.exp(-tp / 0.12);
  };

  // --- the engraving on the barrel bridge
  { const e = new THREE.Mesh(new THREE.PlaneGeometry(13, 3.25), M.engrave); e.position.set(-7.0, 11.6, Z.bridge + 0.505); e.rotation.z = 8 * DEG; e.receiveShadow = true; L.bridge.add(e); }

  // --- the dial and its hands
  { const sh = new THREE.Shape(arcPts(17.0, 0, TAU, 96).slice(0, -1));
    sh.holes.push(new THREE.Path(arcPts(0.5, 0, TAU, 16).slice(0, -1)), new THREE.Path(arcPts(0.3, 0, TAU, 12, CAL.fourth.x, CAL.fourth.y).slice(0, -1)));
    const d = mesh(centreUV(extrude(sh, 0.4, 0.04, Z.dial - 0.4), 35.2), M.dial, "dial"); d.castShadow = false;
    // applied gold pearls at the hours
    const dots = []; for (let i = 0; i < 12; i++) { if (i === 6) continue; const a = i / 12 * TAU, g = new THREE.SphereGeometry(0.27, 14, 8, 0, TAU, 0, Math.PI / 2); g.rotateX(Math.PI / 2); g.translate(16.45 * Math.sin(a), 16.45 * Math.cos(a), Z.dial); dots.push(g); }
    mesh(BGU.mergeGeometries(dots), M.gold, "dial");
    const tri = (pts) => new THREE.Shape(pts.map((q) => V2(q[0], q[1])));
    const ring = (r, hole, y) => { const sh2 = new THREE.Shape(arcPts(r, 0, TAU, 28, 0, y).slice(0, -1)); if (hole) sh2.holes.push(new THREE.Path(arcPts(hole, 0, TAU, 20, 0, y).slice(0, -1))); return sh2; };
    // Breguet hands: a slim stem, an open "moon" near the tip, a fine point
    const hand = (len, wd, z) => BGU.mergeGeometries([
      extrude(ring(0.95, 0.38, 0), 0.14, 0.03, z), extrude(tri([[-wd, 0.7], [wd, 0.7], [wd * 0.55, len * 0.72], [-wd * 0.55, len * 0.72]]), 0.14, 0.03, z),
      extrude(ring(len * 0.075 + 0.25, len * 0.075 - 0.02, len * 0.78), 0.14, 0.03, z), extrude(tri([[-wd * 0.5, len * 0.78 + len * 0.075 + 0.15], [wd * 0.5, len * 0.78 + len * 0.075 + 0.15], [0, len]]), 0.14, 0.03, z),
      extrude(tri([[-wd * 0.8, -0.7], [wd * 0.8, -0.7], [wd * 0.5, -len * 0.16], [-wd * 0.5, -len * 0.16]]), 0.14, 0.03, z)]);
    A.hour = new THREE.Group(); A.minute = new THREE.Group(); A.second = new THREE.Group(); A.second.position.set(CAL.fourth.x, CAL.fourth.y, 0);
    L.hands.add(A.hour, A.minute, A.second);
    mesh(hand(9.6, 0.3, Z.hands), M.bluedHand, A.hour); mesh(hand(14.3, 0.24, Z.hands + 0.3), M.bluedHand, A.minute);
    mesh(BGU.mergeGeometries([extrude(ring(0.42, 0, 0), 0.1, 0.02, Z.hands - 0.1), extrude(tri([[-0.1, 0], [0.1, 0], [0.03, 3.9], [-0.03, 3.9]]), 0.1, 0.02, Z.hands - 0.1),
      extrude(tri([[-0.1, 0], [0.1, 0], [0.2, -1.1], [-0.2, -1.1]]), 0.1, 0.02, Z.hands - 0.1)]), M.bluedHand, A.second);
    mesh(cyl(0.34, Z.hands - 0.1, Z.hands + 0.62, 20), M.gold, "hands"); }

  // --- crystal: a low dome that only adds reflections
  { const prof = []; for (let i = 0; i <= 16; i++) { const r = 17.5 * i / 16; prof.push([Math.max(r, 0.001), 7.9 - 1.0 * (r / 17.5) * (r / 17.5)]); }
    const q = new THREE.Mesh(lathe(prof.reverse(), 64), M.glass); q.renderOrder = 10; L.glass.add(q); }

  // --- the case: polished bezel, brushed band, lugs, the crown on its stem, a strap going off into the dark
  { mesh(lathe([[17.62, -1.1], [17.62, 5.2], [17.45, 5.4], [17.45, 6.9], [18.2, 7.25], [19.6, 6.6], [20.3, 5.3]], 96), M.caseM, "case");
    mesh(lathe([[20.3, 5.3], [20.6, 4.2], [20.6, -1.6], [20.1, -2.6], [17.6, -3.0], [0.01, -3.0]], 96), M.caseB, "case");
    const lug = (sx, sy) => { const sh = new THREE.Shape([V2(8.2, 17.6), V2(11.6, 16.2), V2(12.4, 24.6), V2(11.8, 26.2), V2(9.6, 26.4), V2(9.0, 24.8)].map((q) => V2(q.x * sx, q.y * sy)));
      return extrude(sh, 5.2, 0.5, -2.2); };
    mesh(BGU.mergeGeometries([lug(1, 1), lug(-1, 1), lug(1, -1), lug(-1, -1)]), M.caseM, "case");
    for (const sy of [1, -1]) { const g = new THREE.BoxGeometry(17.6, 46, 2.6, 1, 12, 1), pp = g.attributes.position;
      for (let i = 0; i < pp.count; i++) { const y = pp.getY(i) + 23; pp.setZ(i, pp.getZ(i) - 0.012 * y * y); }
      g.translate(0, 43.5, 0.2); if (sy < 0) g.rotateZ(Math.PI); g.computeVertexNormals(); mesh(g, M.leather, "case"); }
    const {pts} = toothOutline(32, 0.15, {pinion: true});
    const cg = extrude(new THREE.Shape(pts), 2.6, 0.2, 0); cg.rotateY(Math.PI / 2); cg.translate(21.4, 0, 0);
    A.crown = new THREE.Group(); A.crown.position.set(0, 0.35, 0.75); L.case.add(A.crown); mesh(cg, M.caseM, A.crown); }

  // --- update
  const HS = A.hair;
  const upd = (T, opt = {}) => {
    const run = opt.run ?? 1, B = beat(T), Bs = beatStep(T), e = opt.explode ?? 0;
    const a4 = -Bs * TAU / 120;                                                  // fourth wheel: one turn in 120 beats (a minute), clockwise
    const aE = meshAngle(a4, CAL.N4, CAL.NeP, Math.atan2(CAL.escape.y - CAL.fourth.y, CAL.escape.x - CAL.fourth.x));
    const a3 = meshAngle(a4, CAL.N4P, CAL.N3, Math.atan2(CAL.third.y - CAL.fourth.y, CAL.third.x - CAL.fourth.x));
    const aC = meshAngle(a3, CAL.N3P, CAL.Nc, Math.atan2(CAL.centre.y - CAL.third.y, CAL.centre.x - CAL.third.x));
    const aB = meshAngle(aC, CAL.NcP, CAL.Nbarrel, Math.atan2(CAL.barrel.y - CAL.centre.y, CAL.barrel.x - CAL.centre.x));
    A.fourth.rotation.z = a4; A.escape.rotation.z = aE + (opt.escPhase ?? 0); A.third.rotation.z = a3; A.centre.rotation.z = aC; A.barrel.rotation.z = aB;
    // balance and lever
    const amp = 4.5 * run, th = amp * Math.sin(Math.PI * B);
    A.balance.rotation.z = th;
    { const SP = A.spin, K = SP.g.length, shut = 0.8 / 30, ang = (tt) => amp * Math.sin(Math.PI * beat(tt));
      const dA = Math.abs(ang(T + shut / 2) - ang(T - shut / 2)) / (K - 1);
      // how opaque each copy must be for the six together to cover what the part covers while the shutter is open
      const alpha = (width) => { const n = clamp(width / Math.max(dA, 1e-6), 0.02, K); return n >= K ? 1 : 1 - Math.pow(1 - n / K, 1 / n); };
      SP.arm.opacity = alpha(0.2); SP.scr.opacity = alpha(0.07);
      SP.g.forEach((g, k) => { g.rotation.z = ang(T + (k / (K - 1) - 0.5) * shut); }); }
    const psiMax = 7 * DEG, eng = psiMax * CAL.forkL / CAL.rollerR;
    // the lever lies to one side between ticks and is thrown across as the balance passes its centre
    const k = Math.floor(B + 0.5), side = (k % 2 ? 1 : -1), near = clamp((th * (side)) / eng, -1, 1);
    A.fork.rotation.z = CAL.lineA + psiMax * (Math.abs(th) < eng && run > 0.02 ? -clamp(th / eng, -1, 1) : -Math.sign(th || side));
    A.rollerPin.position.set(-CAL.rollerR * Math.cos(CAL.lineA), -CAL.rollerR * Math.sin(CAL.lineA), 0);
    // hairspring: fixed at the stud outside, turning with the collet inside; the coils crowd and open as it breathes
    const pos = HS.pos, n = HS.rings, turns = 12, r0 = 0.5, r1 = 3.5, hh = 0.11, tk = 0.03, gam = 1 + 0.085 * th;
    for (let i = 0; i < n; i++) {
      const s = i / (n - 1), a = 1.0 - (turns * TAU - th) * s, r = r1 + (r0 - r1) * Math.pow(s, gam), cx = Math.cos(a), sy = Math.sin(a), q = i * 12;
      pos[q] = (r - tk) * cx; pos[q + 1] = (r - tk) * sy; pos[q + 2] = HS.z - hh;
      pos[q + 3] = (r - tk) * cx; pos[q + 4] = (r - tk) * sy; pos[q + 5] = HS.z + hh;
      pos[q + 6] = (r + tk) * cx; pos[q + 7] = (r + tk) * sy; pos[q + 8] = HS.z + hh;
      pos[q + 9] = (r + tk) * cx; pos[q + 10] = (r + tk) * sy; pos[q + 11] = HS.z - hh;
    }
    HS.mesh.geometry.attributes.position.needsUpdate = true;
    // winding: one tooth of the ratchet wheel for each click of the score
    const nc = hitCount("ratchet", T), ca = hitAge("ratchet", T), w = nc - Math.exp(-ca / 0.03);
    const aR = -w * TAU / CAL.Nr;
    A.ratchet.rotation.z = aR; A.crownW.rotation.z = meshAngle(aR, CAL.Nr, CAL.Ncw, Math.atan2(CAL.crownW.y - CAL.barrel.y, CAL.crownW.x - CAL.barrel.x));
    A.click.rotation.z = A.clickBase + 0.14 * Math.exp(-ca / 0.05);
    A.stem.rotation.x = -w * 0.5; A.crown.rotation.x = -w * 0.5;
    // hands: 10:08 and no seconds when the film begins
    A.second.rotation.z = a4; A.minute.rotation.z = -(8 / 60) * TAU + a4 / 60; A.hour.rotation.z = -(10 / 12 + 8 / 720) * TAU + a4 / 720;
    const da = opt.dial ?? 1;
    M.dial.opacity = da; L.dial.visible = da > 0.003;
    if (M.dial.transparent !== (da < 0.999)) { M.dial.transparent = da < 0.999; M.dial.needsUpdate = true; }
    // what a closed dial hides is not drawn at all
    const under = da < 0.999 || e > 0.001 || !!opt.open;
    for (const nme of ["plate", "barrel", "l2", "l3", "poly", "lowbridge", "bridge", "wind", "balance", "cock"]) L[nme].visible = under;
    // three against four: twelve teeth a bar; the work stops with everything else in the silent bar
    const Tp = T < 134 ? T : T < 136 ? 134 : T - 2;
    const aPA = A.pinAngA - (Tp / BAR) * TAU / 3;
    A.polyA.rotation.z = aPA; A.polyB.rotation.z = meshAngle(aPA, CAL.NpA, CAL.NpB, Math.atan2(CAL.polyB.y - CAL.polyA.y, CAL.polyB.x - CAL.polyA.x));
    upd.glint = {three: AU.hits.three ? hammer(H.three, AU.hits.three.t, T) : 0, four: hammer(H.four, fourT, T), chime: AU.hits.chime ? hammer(H.chime, AU.hits.chime.t, T) : 0};
    // jewels glow a little on each tick
    M.ruby.emissiveIntensity = 0.7 + 1.6 * tickEnv(T, 0.16) * run + (opt.glow ?? 0);

    const off = {plate: -9.5, barrel: -6.6, l2: -3.8, poly: -2.0, l3: 0, lowbridge: 2.8, balance: 5.0, bridge: 7.2, wind: 9.4, cock: 10.4, dial: 14.6, hands: 17.6, glass: 21, case: -9.5};
    for (const nme of layerNames) L[nme].position.z = e * off[nme];
    // assembly: parts come down out of the blur in front of the lens and seat themselves (opt.place: name -> 0..1)
    const pl = opt.place;
    for (const nme in PARTS) { const u = pl ? (pl[nme] ?? 1) : 1, q = PARTS[nme]; q.visible = u > 0; const dz = (1 - easeOut(u)) * 26; if (q.parent === root) q.position.z += dz; else q.position.z = dz; }
  };
  const PARTS = {barrel: A.barrel, centre: A.centre, third: A.third, fourth: A.fourth, escape: A.escape, pallet: A.pallet, balance: L.balance, lowbridge: L.lowbridge, bridge: L.bridge, wind: L.wind, cock: L.cock, poly: L.poly};
  return {root, L, A, H, J, update: upd};
}

// ---------- the frame: scene -> depth of field -> bloom -> tone curve, grade, vignette, grain ----------
// all shots but the first and the last (the whole watch, with fine print) are drawn at 88 % size and enlarged: a quarter fewer pixels to shade
const SCALE = {winding: 1, coda: 1};
const FSQ_VERT = "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }";
// depth of field in two steps: a gathered blur at half size, then laid over the sharp picture where the lens is out of focus
const DOF_BLUR = /* glsl */`
  #include <packing>
  varying vec2 vUv; uniform sampler2D tColor, tDepth; uniform vec2 uRes; uniform float uNear, uFar, uFocus, uAperture, uMaxR;
  float viewZ(vec2 uv){ return -perspectiveDepthToViewZ(texture2D(tDepth, uv).x, uNear, uFar); }
  float coc(float z){ return clamp(uAperture * abs(z - uFocus) / max(z, 0.001), 0.0, uMaxR); }
  void main(){
    float z0 = viewZ(vUv), r0 = coc(z0);
    vec3 acc = texture2D(tColor, vUv).rgb; float wsum = 1.0, cov = r0;
    float rad = max(r0, uMaxR * 0.6);
    for (int i = 1; i < TAPS; i++) {
      float fi = float(i), rr = sqrt(fi / float(TAPS)) * rad, th = fi * 2.39996323;
      vec2 uv = vUv + vec2(cos(th), sin(th)) * rr / uRes;
      float zs = viewZ(uv), rs = coc(zs);
      // a sample counts if its own blur reaches this pixel; what lies in front bleeds over, sharp things behind do not
      float w = smoothstep(rr - 1.0, rr + 1.0, zs > z0 ? min(rs, r0 + 1.0) : rs);
      acc += min(texture2D(tColor, uv).rgb, vec3(24.0)) * w; wsum += w; cov = max(cov, rs * w);
    }
    gl_FragColor = vec4(acc / wsum, cov);
  }`;
const DOF_MIX = /* glsl */`
  varying vec2 vUv; uniform sampler2D tColor, tBlur;
  void main(){ vec4 b = texture2D(tBlur, vUv); vec3 c = texture2D(tColor, vUv).rgb; gl_FragColor = vec4(mix(c, b.rgb, smoothstep(0.6, 2.6, b.a)), 1.0); }`;
const DEPTH_ONLY = new THREE.MeshBasicMaterial({colorWrite: false});
class ScenePass extends Pass {
  constructor(w, h) {
    super();
    const sc = Q.scale ?? (SCALE[mode] ?? 0.88), sw = Math.round(w * sc), shh = Math.round(h * sc);
    this.rt = new THREE.WebGLRenderTarget(sw, shh, {type: THREE.HalfFloatType, samples: (Q.msaa ?? 0), depthTexture: new THREE.DepthTexture(sw, shh, THREE.UnsignedIntType)});
    this.half = new THREE.WebGLRenderTarget(sw >> 1, shh >> 1, {type: THREE.HalfFloatType, depthBuffer: false});
    this.blur = new THREE.ShaderMaterial({defines: {TAPS: Q.taps ?? 20}, uniforms: {tColor: {value: null}, tDepth: {value: null}, uRes: {value: V2(w, h)}, uNear: {value: 1}, uFar: {value: 100}, uFocus: {value: 30}, uAperture: {value: 0}, uMaxR: {value: 9}},
      vertexShader: FSQ_VERT, fragmentShader: DOF_BLUR, depthTest: false, depthWrite: false});
    this.mix = new THREE.ShaderMaterial({uniforms: {tColor: {value: null}, tBlur: {value: null}}, vertexShader: FSQ_VERT, fragmentShader: DOF_MIX, depthTest: false, depthWrite: false});
    this.copy = new THREE.ShaderMaterial({uniforms: {tColor: {value: null}}, vertexShader: FSQ_VERT, fragmentShader: "varying vec2 vUv; uniform sampler2D tColor; void main(){ gl_FragColor = vec4(texture2D(tColor, vUv).rgb, 1.0); }", depthTest: false, depthWrite: false});
    this.fsq = new FullScreenQuad(this.blur); this.needsSwap = true; this.hide = [];
  }
  render(renderer, writeBuffer) {
    renderer.setRenderTarget(this.rt); renderer.clear();
    if (Q.pre ?? false) {                                   // depth first, so that every pixel is shaded once
      for (const o of this.hide) o.visible = false;
      S.overrideMaterial = DEPTH_ONLY; renderer.render(S, C); S.overrideMaterial = null;
      for (const o of this.hide) o.visible = true;
      renderer.autoClear = false;
    }
    renderer.shadowMap.needsUpdate = true;
    renderer.render(S, C); renderer.autoClear = true;
    const u = this.blur.uniforms;
    if (u.uAperture.value > 0) {
      u.tColor.value = this.rt.texture; u.tDepth.value = this.rt.depthTexture; u.uNear.value = C.near; u.uFar.value = C.far;
      this.fsq.material = this.blur; renderer.setRenderTarget(this.half); this.fsq.render(renderer);
      this.mix.uniforms.tColor.value = this.rt.texture; this.mix.uniforms.tBlur.value = this.half.texture; this.fsq.material = this.mix;
    } else { this.copy.uniforms.tColor.value = this.rt.texture; this.fsq.material = this.copy; }
    renderer.setRenderTarget(this.renderToScreen ? null : writeBuffer); this.fsq.render(renderer);
  }
}
const FIN = {
  uniforms: {tDiffuse: {value: null}, uExp: {value: 1}, uLift: {value: new THREE.Color(0, 0, 0)}, uGain: {value: new THREE.Color(1, 1, 1)}, uSat: {value: 1}, uVig: {value: 0.5},
    uFade: {value: 1}, uFlash: {value: new THREE.Color(0, 0, 0)}, uRes: {value: V2(1280, 720)}, uCA: {value: 0.6}},
  vertexShader: FSQ_VERT,
  fragmentShader: /* glsl */`
    varying vec2 vUv; uniform sampler2D tDiffuse; uniform float uExp, uSat, uVig, uFade, uCA; uniform vec3 uLift, uGain, uFlash; uniform vec2 uRes;
    vec3 aces(vec3 x){ return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }
    void main(){
      vec2 q = vUv - 0.5; float r2 = dot(q, q * vec2(1.0, uRes.y / uRes.x * 1.4));
      vec2 ca = q * r2 * uCA * 0.012;
      vec3 c = vec3(texture2D(tDiffuse, vUv + ca).r, texture2D(tDiffuse, vUv).g, texture2D(tDiffuse, vUv - ca).b);
      c = c * uExp + uFlash;
      c *= mix(1.0, smoothstep(0.75, 0.12, r2 * 1.9), uVig);
      c = aces(c * uGain);
      float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
      c = mix(vec3(l), c, uSat);
      c = c + uLift * (1.0 - c);
      c = pow(c, vec3(1.0 / 2.2));
      gl_FragColor = vec4(c * uFade, 1.0);
    }`,
};
// last: smooth the stair-steps on edges (FXAA on the finished picture), then lay the film grain over it
const AA = {
  uniforms: {tDiffuse: {value: null}, uRes: {value: V2(1280, 720)}, uGrain: {value: 0.03}, uSeed: {value: 0}},
  vertexShader: FSQ_VERT,
  fragmentShader: /* glsl */`
    varying vec2 vUv; uniform sampler2D tDiffuse; uniform vec2 uRes; uniform float uGrain, uSeed;
    float h(vec2 p){ vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
    float lum(vec3 c){ return dot(c, vec3(0.299, 0.587, 0.114)); }
    void main(){
      vec2 px = 1.0 / uRes;
      vec3 cM = texture2D(tDiffuse, vUv).rgb;
      float lM = lum(cM), lNW = lum(texture2D(tDiffuse, vUv + vec2(-1.0, 1.0) * px).rgb), lNE = lum(texture2D(tDiffuse, vUv + vec2(1.0, 1.0) * px).rgb),
        lSW = lum(texture2D(tDiffuse, vUv + vec2(-1.0, -1.0) * px).rgb), lSE = lum(texture2D(tDiffuse, vUv + vec2(1.0, -1.0) * px).rgb);
      float lMin = min(lM, min(min(lNW, lNE), min(lSW, lSE))), lMax = max(lM, max(max(lNW, lNE), max(lSW, lSE)));
      vec3 c = cM;
      if (lMax - lMin > max(0.03, lMax * 0.1)) {
        vec2 dir = vec2(-((lNW + lNE) - (lSW + lSE)), (lNW + lSW) - (lNE + lSE));
        float red = max((lNW + lNE + lSW + lSE) * 0.03125, 1.0 / 128.0), rc = 1.0 / (min(abs(dir.x), abs(dir.y)) + red);
        dir = clamp(dir * rc, -8.0, 8.0) * px;
        vec3 a = 0.5 * (texture2D(tDiffuse, vUv + dir * (1.0 / 3.0 - 0.5)).rgb + texture2D(tDiffuse, vUv + dir * (2.0 / 3.0 - 0.5)).rgb);
        vec3 b = a * 0.5 + 0.25 * (texture2D(tDiffuse, vUv - dir * 0.5).rgb + texture2D(tDiffuse, vUv + dir * 0.5).rgb);
        float lB = lum(b); c = (lB < lMin || lB > lMax) ? a : b;
      }
      float l = lum(c), g = h(gl_FragCoord.xy + uSeed * 7.31) + h(gl_FragCoord.xy * 1.7 + uSeed * 3.17 + 91.0) - 1.0;
      c += g * uGrain * (0.5 + 0.8 * (1.0 - l)) * smoothstep(0.0, 0.04, l + 0.02);
      gl_FragColor = vec4(c, 1.0);
    }`,
};
function finish(T, o = {}) {
  const u = fin.uniforms;
  u.uExp.value = o.exp ?? 1; u.uSat.value = o.sat ?? 1; u.uVig.value = o.vig ?? 0.55; aa.uniforms.uGrain.value = (o.grain ?? 0.028) * (o.fade ?? 1); aa.uniforms.uSeed.value = Math.round(T * 30) % 4096; u.uFade.value = o.fade ?? 1; u.uCA.value = o.ca ?? 0.5;
  u.uLift.value.copy(o.lift ?? BLACK); u.uGain.value.copy(o.gain ?? ONE);
  if (o.flash) u.uFlash.value.copy(o.flashCol ?? ONE).multiplyScalar(o.flash); else u.uFlash.value.setRGB(0, 0, 0);
  bloom.strength = o.bloom ?? 0.35; bloom.radius = o.bloomR ?? 0.5; bloom.threshold = o.bloomT ?? 1.0;
  const d = scenePass.blur.uniforms; d.uFocus.value = o.focus ?? 30; d.uAperture.value = (Q.dof ?? true) ? (o.aperture ?? 0) * H / 720 : 0; d.uMaxR.value = (o.maxR ?? 9) * H / 720;
}
const BLACK = hx(0x000000), ONE = new THREE.Color(1, 1, 1);
const VA = new THREE.Vector3(), VB = new THREE.Vector3();
function setCam(px, py, pz, tx, ty, tz, roll = 0, fov = 30, up = null) {
  C.position.set(px, py, pz); C.up.set(0, 1, 0); if (up) C.up.set(up[0], up[1], up[2]);
  C.lookAt(tx, ty, tz); if (roll) C.rotateZ(roll);
  if (C.fov !== fov) { C.fov = fov; }
  C.updateProjectionMatrix();
  return Math.hypot(px - tx, py - ty, pz - tz);
}
// the key light: one shadowed directional light that follows the studio's big box
function makeKey(col = 0xfff1e0, int = 0.7, dir = [-0.5, 0.62, 0.6], size = 22) {
  const l = new THREE.DirectionalLight(col, int); l.position.set(dir[0] * 60, dir[1] * 60, dir[2] * 60);
  l.castShadow = true; l.shadow.mapSize.set(Q.sm ?? 2048, Q.sm ?? 2048); const c = l.shadow.camera; c.left = -size; c.right = size; c.top = size; c.bottom = -size; c.near = 10; c.far = 120; l.shadow.bias = -0.0004; l.shadow.normalBias = 0.03; l.shadow.radius = 3;
  S.add(l); S.add(l.target); return l;
}

// ---------- glints and dust ----------
function spriteTex(kind) {
  const N = 128, c = document.createElement("canvas"); c.width = c.height = N; const g = c.getContext("2d");
  const grd = g.createRadialGradient(N / 2, N / 2, 0, N / 2, N / 2, N / 2);
  if (kind === "dust") { grd.addColorStop(0, "rgba(255,255,255,1)"); grd.addColorStop(0.35, "rgba(255,255,255,0.35)"); grd.addColorStop(1, "rgba(255,255,255,0)"); g.fillStyle = grd; g.fillRect(0, 0, N, N); }
  else {
    grd.addColorStop(0, "rgba(255,255,255,1)"); grd.addColorStop(0.05, "rgba(255,255,255,0.55)"); grd.addColorStop(0.18, "rgba(255,255,255,0.1)"); grd.addColorStop(0.5, "rgba(255,255,255,0.02)"); grd.addColorStop(1, "rgba(255,255,255,0)"); g.fillStyle = grd; g.fillRect(0, 0, N, N);
    g.globalCompositeOperation = "lighter";
    for (const [ang, len, wd] of [[0, 0.9, 1.0], [Math.PI / 2, 0.55, 1.0]]) {
      g.save(); g.translate(N / 2, N / 2); g.rotate(ang); const lg = g.createLinearGradient(-N / 2 * len, 0, N / 2 * len, 0);
      lg.addColorStop(0, "rgba(255,255,255,0)"); lg.addColorStop(0.5, "rgba(255,255,255,0.45)"); lg.addColorStop(1, "rgba(255,255,255,0)"); g.fillStyle = lg; g.fillRect(-N / 2 * len, -wd / 2, N * len, wd); g.restore(); }
  }
  return new THREE.CanvasTexture(c);
}
function makeFlares(n) {
  const tex = spriteTex("flare"), f = [];
  for (let i = 0; i < n; i++) { const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: tex, blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false, transparent: true})); sp.visible = false; sp.renderOrder = 20; S.add(sp); f.push(sp); }
  return f;
}
function flare(f, i, pos, size, amt, col = WARMW) { const sp = f[i]; if (!sp) return; sp.visible = amt > 0.01; if (!sp.visible) return; sp.position.copy(pos); sp.scale.setScalar(size * 0.6 * (0.6 + 0.4 * Math.min(amt, 1.5))); sp.material.color.copy(col).multiplyScalar(amt); }
function makeDust(n, box, size, seed = 1) {
  const pos = new Float32Array(n * 3), g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const m = new THREE.PointsMaterial({map: spriteTex("dust"), size, sizeAttenuation: true, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, color: 0xffffff});
  const pts = new THREE.Points(g, m); pts.frustumCulled = false; S.add(pts);
  return {pts, pos, n, box, seed};
}
function updateDust(d, T, col, amt, drift = 0.15) {
  const [bx, by, bz, cx, cy, cz] = d.box;
  for (let i = 0; i < d.n; i++) {
    const wrap = (v, w) => ((v % w) + w) % w - w / 2;
    d.pos[i * 3] = cx + wrap(hash1(i, d.seed) * bx + T * drift * (hash1(i, d.seed + 7) - 0.5), bx);
    d.pos[i * 3 + 1] = cy + wrap(hash1(i, d.seed + 1) * by + T * drift * (hash1(i, d.seed + 8) - 0.5), by);
    d.pos[i * 3 + 2] = cz + wrap(hash1(i, d.seed + 2) * bz + T * drift * 0.6 * (hash1(i, d.seed + 9) - 0.2), bz);
  }
  d.pts.geometry.attributes.position.needsUpdate = true; d.pts.material.color.copy(col).multiplyScalar(amt);
}
const WARMW = hx(0xfff0d8), GOLDC = hx(0xffc860), COOLW = hx(0xd8e8ff), AMBER = hx(0xff9a3c), RUBYC = hx(0xff3040), BLUEC = hx(0x5080ff);
const V3 = (x, y, z) => new THREE.Vector3(x, y, z);
// a point moving through keyframes [[t, x, y, z], ...] with eased segments
function path(keys, t) {
  if (t <= keys[0][0]) return keys[0].slice(1);
  for (let i = 0; i < keys.length - 1; i++) if (t <= keys[i + 1][0]) { const a = keys[i], b = keys[i + 1], u = sstep(0, 1, (t - a[0]) / (b[0] - a[0])); return a.slice(1).map((v, k) => mix(v, b[k + 1], u)); }
  return keys[keys.length - 1].slice(1);
}
// one smooth move from a to b over the whole shot (no stops in the middle)
const glide = (a, b, u) => a.map((v, k) => mix(v, b[k], ease(u)));

// ====================================================================================================
// Shots. Watch coordinates are millimetres: x to three o'clock, y to twelve, z out of the dial towards the viewer.
const MODES = {};
function watchWorld(studio = "warm", bg = 0x030304, keyInt = 0.7) {
  S.environment = STUDIO[studio](); S.background = hx(bg);
  O.w = buildWatch(); S.add(O.w.root);
  O.key = makeKey(0xfff1e0, keyInt);
  O.fl = makeFlares(14);
}
const movementOnly = (on = true) => { const L = O.w.L; L.hands.visible = L.glass.visible = L.case.visible = !on; };
// light that answers the music: great drums and booms lift the whole studio a little, never the camera
function pulse(T, base = 1, k = 0.28) { const v = base * (1 + k * Math.min(1.3, env("taiko", T, 0.35) + 0.8 * env("boom", T, 0.8))); S.environmentIntensity = v; return v; }
// Turn the studio so that its big soft box sits `off` radians (in azimuth) from where the flat plates mirror the
// camera: near 0 the plates blaze, near 1.3 they show the box's falling edge, the stripes and the graining.
function envTrack(camAz, off) { S.environmentRotation.set(0, 0, (Q.envsign ?? -1) * (camAz + Math.PI + off - 2.25)); }

// ---- hero and wide: test shots used while the look was developed (not in the film) ----
MODES.hero = {
  build() { watchWorld(); movementOnly(); },
  frame(T, t) {
    O.w.update(T, {dial: 0});
    const p = CAL.pallet;
    const d = setCam(p.x - 5 + 1.5 * Math.sin(t * 0.2), p.y - 13, 15, p.x - 0.6, p.y + 0.6, 2.2, 0.0, 30, [0, 0, 1]);
    finish(T, {exp: 1.0, focus: d, aperture: 26, maxR: 10, bloom: 0.4, vig: 0.6});
  },
};
// test: straight down on the escapement
MODES.esctop = { build() { watchWorld(); movementOnly(); O.w.L.cock.visible = false; }, frame(T, t) { O.w.update(T, {dial: 0, open: 1}); O.w.L.cock.visible = false; O.w.L.balance.visible = !(Q.nobal);
  const p = CAL.pallet; const d = setCam(p.x - 0.5, p.y - 0.01, 16, p.x - 0.5, p.y, 1.8, 0, 30); finish(T, {focus: d, aperture: 0, vig: 0.2}); } };
MODES.blank = { build() { S.background = hx(0x202020); }, frame(T, t) { setCam(0, 0, 50, 0, 0, 0); finish(T, {}); } };
MODES.wide = {
  build() { watchWorld(); },
  frame(T, t) {
    const full = t < 2;
    O.w.L.hands.visible = O.w.L.glass.visible = O.w.L.case.visible = full || t > 4;
    O.w.update(T, {explode: (t > 4 ? 1 : 0), dial: full || t > 4 ? 1 : 0});
    const d = t > 4 ? setCam(46, -62, 40, 0, 0, 5, 0, 40, [0, 0, 1]) : setCam(0, -12, full ? 78 : 52, 0, 0, 0, 0, 40, [0, 0, 1]);
    finish(T, {exp: 1.0, focus: d, aperture: 0, bloom: 0.4, vig: 0.5});
  },
};

// ---- 01 winding (bars 0-8): the watch in the dark; the crown is wound; the title; at bar 4 it starts to tick ----
MODES.winding = {
  build() { watchWorld("cool", 0x020203, 0.5); },
  frame(T, t) {
    const run = sstep(4 * BAR - 0.2, 6 * BAR, T);
    O.w.update(T, {run});
    const u = t / (8 * BAR);
    const c = glide([-13, -36, 92, -19, -1, 2], [-3, -22, 66, -14, -0.5, 3], u);
    const d = setCam(c[0], c[1], c[2], c[3], c[4], c[5], 0, 30, [0, 0.35, 1]);
    const wake = sstep(0, 1.0 * BAR, t), rat = env("ratchet", T, 0.12);
    pulse(T, 0.25 + 0.75 * wake, 0.5); O.key.intensity = 0.5 * wake;
    S.environmentRotation.set(0, 0, -0.5 + 0.5 * ease(u));
    flare(O.fl, 0, VA.set(21.6 + 1.3, 0.35, 2.2), 6, 0.4 * rat * wake, COOLW);
    flare(O.fl, 1, VA.set(0, -8.3, 6.2), 5, 0.6 * tickEnv(T, 0.1) * run, WARMW);
    flare(O.fl, 2, VA.set(-9, 12, 8), 12, 0.8 * noteEnv("chime", T, 1.2) * (T > 14 ? 1 : 0), GOLDC);
    const warm = sstep(4 * BAR, 8 * BAR, t);
    finish(T, {exp: 0.95 * sstep(0, 0.7, t) + 0.25 * env("boom", T, 0.5) * sstep(0, 0.3, t), focus: d, aperture: 14, maxR: 7, bloom: 0.5, vig: 0.75,
      gain: lc(hx(0xa9c0ff), hx(0xfff4e4), warm), lift: lc(hx(0x02040a), hx(0x040302), warm), sat: 0.9 + 0.1 * warm});
    const a = sstep(1.2 * BAR, 2.2 * BAR, t) * (1 - sstep(6.2 * BAR, 7.2 * BAR, t));
    titleEl.style.opacity = a.toFixed(3); titleEl.style.display = a > 0.002 ? "block" : "none";
    titleEl.firstChild.style.letterSpacing = (0.26 + 0.03 * sstep(1.2 * BAR, 7.2 * BAR, t)).toFixed(4) + "em";
  },
};

// ---- 02 dial (bars 8-16): macro over the dial; a pearl of gold glints for each note of the music box; the push in at the small seconds ----
MODES.dial = {
  build() { watchWorld("warm", 0x030303, 0.5); O.w.L.glass.visible = false; },
  frame(T, t) {
    O.w.update(T, {});
    const u = t / (8 * BAR), push = Math.pow(sstep(6.4 * BAR, 8 * BAR, t), 2);
    const c = glide([-13, 3, 17, -1, 7, 5.3], [5, -21, 12, 0, -7.4, 5.3], u);
    const cz = mix(c[2], 6.4, push), cx = mix(c[0], 0.3, push), cy = mix(c[1], -9.6, push);
    const d = setCam(cx, cy, cz, mix(c[3], 0, push), mix(c[4], -8.3, push), c[5], 0, 34, [0, 0.5, 1]);
    pulse(T, 1.0, 0.2); S.environmentRotation.set(0, 0, 0.25 * Math.sin(t * 0.21) + 0.6 * u);
    // the music box lights the hour pearls: each pitch has its hour
    const nb = AU.notes.box;
    if (nb) for (let k = 0; k < 6; k++) { const i = lastIdx(nb.t, T) - k; if (i < 0 || nb.t[i] < 15) { flare(O.fl, k, VA, 1, 0); continue; }
      let h = (nb.p[i] * 7) % 12; if (h === 6) h = 5; const a = h / 12 * TAU, age = T - nb.t[i];
      flare(O.fl, k, VA.set(16.45 * Math.sin(a), 16.45 * Math.cos(a), 5.5), 4.5, 1.6 * Math.exp(-age / 0.9), GOLDC); }
    flare(O.fl, 7, VA.set(0, -8.3, 5.8), 2.2, 0.5 * tickEnv(T, 0.08), WARMW);
    finish(T, {exp: 1.05 + 0.5 * push, focus: d * (1 - 0.1 * push), aperture: 30 - 8 * push, maxR: 11, bloom: 0.45 + 0.5 * push, vig: 0.6, gain: hx(0xfff3e2), lift: hx(0x050403),
      flash: 0.25 * Math.exp(-t / 0.5) + 1.4 * Math.pow(push, 6), flashCol: WARMW});
  },
};

// ---- 03 through (bars 16-24): under the dial. The movement assembles, a layer for each entry of the music ----
MODES.through = {
  build() { watchWorld("warm", 0x030304, 0.45); movementOnly(); },
  frame(T, t) {
    const b = t / BAR, at = (bar, len = 0.9) => clamp((b - bar) / len);
    const place = {barrel: at(0.5), centre: at(1), fourth: at(2), third: at(3), poly: at(3.5), escape: at(4), pallet: at(4.5), balance: at(5), lowbridge: at(5.75), bridge: at(6.25), wind: at(6.9), cock: at(7.2, 0.7)};
    O.w.update(T, {dial: 0, place, run: at(5)});
    const u = t / (8 * BAR);
    const c = glide([0.3, -9.6, 14, 0, -8.3, 0, 34], [-17, -34, 27, -0.5, -1.5, 1.5, 30], Math.pow(u, 0.8));
    const d = setCam(c[0], c[1], c[2], c[3], c[4], c[5], 0, c[6], [0, 0.4, 1]);
    pulse(T, 0.85 + 0.25 * u, 0.3); S.environmentRotation.set(0, 0, 0.5 - 0.5 * u);
    // a glint where each part seats itself
    const seats = [[1.9, CAL.centre], [2.9, CAL.fourth], [3.9, CAL.third], [4.9, CAL.escape], [5.9, CAL.balance], [7.15, CAL.barrel], [7.9, CAL.balance]];
    seats.forEach(([bar, p], i) => flare(O.fl, i, VA.set(p.x, p.y, 3.2), 6, b > bar ? 1.5 * Math.exp(-(b - bar) * BAR / 0.25) : 0, WARMW));
    finish(T, {exp: 1.0, focus: d, aperture: 20, maxR: 10, bloom: 0.45, vig: 0.6, gain: hx(0xfff6ea), flash: 1.6 * Math.exp(-t / 0.35), flashCol: WARMW});
  },
};

// ---- 04 escapement (bars 24-32): the heart, close. Escape wheel, pallets, the balance and its breathing spring ----
MODES.escapement = {
  build() { watchWorld("warm", 0x030303, 0.5); movementOnly(); },
  frame(T, t) {
    O.w.update(T, {dial: 0});
    const u = t / (8 * BAR), e = CAL.escape, bal = CAL.balance, p = CAL.pallet;
    const c = glide([e.x + 4.5, e.y - 10.5, 6.4, p.x + 0.3, p.y - 0.4, 1.9], [bal.x - 6.5, bal.y - 10, 14.5, bal.x + 0.6, bal.y + 0.4, 3.0], u);
    const d = setCam(c[0], c[1], c[2], c[3], c[4], c[5], 0, 32, [0, 0, 1]);
    pulse(T, 1.0, 0.35); S.environmentRotation.set(0, 0, 0.35 * Math.sin(t * 0.3));
    const tk = tickEnv(T, 0.1);
    flare(O.fl, 0, VA.set(p.x, p.y, 2.4), 2.4, 0.9 * tk, RUBYC);
    flare(O.fl, 1, VA.set(bal.x, bal.y, 4.6), 2.6, 0.35 * tk + 0.5 * env("taiko", T, 0.5), RUBYC);
    finish(T, {exp: 1.0 + 0.1 * env("taiko", T, 0.4), focus: d, aperture: 30, maxR: 11, bloom: 0.45, vig: 0.65, gain: hx(0xfff1dc), lift: hx(0x050302), flash: 0.5 * Math.exp(-t / 0.4), flashCol: GOLDC});
  },
};

// ---- 05 cathedral (bars 32-40): the same movement from inside, at the height of a grain of dust: wheels are vaults, arbors columns ----
function cathedralWorld() {
  watchWorld("warm", 0x2a1608, 1.0); movementOnly();          // the haze has the colour of the distance
  S.fog = new THREE.FogExp2(0x2a1608, 0.045);
  O.dust = makeDust(260, [18, 18, 3, 0, -5, 1.4], 0.07, 3);
  C.near = 0.05; C.far = 120;
}
MODES.cathedral = {
  build() { cathedralWorld(); },
  frame(T, t) {
    O.w.update(T, {dial: 0});
    const b = t / BAR, cut = b >= 4;
    let c;
    if (!cut) c = glide([-0.6, -13.6, 0.5, 1.2, -4.0, 1.75, 62], [-0.2, -9.9, 0.62, 1.8, 0, 1.9, 62], b / 4);   // along the plate, under the fourth wheel, towards the centre
    else c = glide([4.9, -9.0, 0.35, 2.2, -5.2, 2.2, 58], [5.4, -6.6, 2.9, 1.6, -4.9, 1.75, 58], (b - 4) / 4);      // up past the third wheel and the pinion it drives
    const d = setCam(c[0], c[1], c[2], c[3], c[4], c[5], 0, c[6], [0, 0, 1]);
    const tk = env("taiko", T, 0.5), bm = env("boom", T, 0.9);
    pulse(T, 1.2, 0.4); O.key.intensity = 0.8 + 0.3 * tk; S.environmentRotation.set(0, 0, 0.6 + 0.06 * t);
    updateDust(O.dust, T, AMBER, 0.5 + 0.6 * tk, 0.12);
    S.fog.density = 0.036 - 0.006 * tk;
    flare(O.fl, 0, VA.set(CAL.centre.x, CAL.centre.y, 0.3), 1.6, 0.8 * tickEnv(T, 0.12), RUBYC);
    flare(O.fl, 1, VA.set(CAL.third.x, CAL.third.y, 0.3), 1.6, 0.8 * tickEnv(T, 0.12), RUBYC);
    flare(O.fl, 2, VA.set(O.w.H.chime.hit.x, O.w.H.chime.hit.y, 2), 9, 1.2 * noteEnv("chime", T, 0.9), GOLDC);
    const cutFlash = cut ? Math.exp(-(t - 4 * BAR) / 0.3) : Math.exp(-t / 0.4);
    finish(T, {exp: 1.4 + 0.15 * tk, focus: d, aperture: 5, maxR: 5, bloom: 0.5, bloomT: 1.0, vig: 0.75, gain: hx(0xffe2bd), lift: hx(0x070402), sat: 1.05, flash: 0.22 * cutFlash, flashCol: AMBER});
  },
};

// ---- 06 three against four (bars 40-48): 36 teeth against 48, three pins against four, two hammers on the gong ----
MODES.threefour = {
  build() { cathedralWorld(); S.fog.color.set(0x2c1206); S.background.set(0x180a04); },
  frame(T, t) {
    O.w.update(T, {dial: 0});
    const b = t / BAR, A = CAL.polyA, Bp = CAL.polyB, mx = (A.x + Bp.x) / 2, my = (A.y + Bp.y) / 2, u = b / 8;
    const c = glide([mx + 7.4, my - 4.6, 5.2, mx - 0.4, my + 0.6, 1.0, 46], [mx + 10.5, my - 10.5, 13.5, mx - 1.2, my + 1.4, 1.0, 42], Math.pow(u, 1.2));
    const d = setCam(c[0], c[1], c[2], c[3], c[4], c[5], 0, c[6], [0, 0, 1]);
    const tk = env("taiko", T, 0.5), g = O.w.update.glint;
    pulse(T, 1.1, 0.4); O.key.intensity = 0.5 + 0.3 * tk; S.environmentRotation.set(0, 0, 1.2 + 0.05 * t);
    updateDust(O.dust, T, AMBER, 0.4 + 0.5 * tk, 0.12);
    S.fog.density = 0.022 - 0.008 * u;
    flare(O.fl, 0, O.w.H.three.hit, 1.8, 0.8 * g.three, hx(0xff7a50));
    flare(O.fl, 1, O.w.H.four.hit, 1.8, 0.7 * g.four, COOLW);
    finish(T, {exp: 1.15 + 0.15 * tk - 0.12 * u, focus: d, aperture: 12 - 6 * u, maxR: 8, bloom: 0.3, bloomT: 1.25, vig: 0.8, gain: lc(hx(0xffe2bd), hx(0xffcfa0), u), lift: hx(0x080302), sat: 1.08,
      flash: 0.2 * Math.exp(-t / 0.4) + 0.3 * sstep(7.6 * BAR, 8 * BAR, t), flashCol: AMBER});
  },
};

// ---- the orrery: an orrery is a clock. Sun, six planets on their arms over a night-blue disc with gold stars ----
const PLANETS = [   // name, orbit radius, size, period in years, material, gear ratio it stands for
  ["mercury", 11, 1.5, 20 / 83, "steel"], ["venus", 17, 2.3, 8 / 13, "gold"], ["earth", 24, 2.5, 1, "blued"],
  ["mars", 31.5, 2.0, 79 / 42, "ruby"], ["jupiter", 42.5, 4.8, 83 / 7, "brass"], ["saturn", 54, 4.0, 59 / 2, "rose"]];
const YEAR = 8 * BAR;                                         // the Earth goes round once in eight bars
function nightTexture() {
  const N = 2048, c = document.createElement("canvas"); c.width = c.height = N; const g = c.getContext("2d"), k = N / 132;
  const bg = g.createRadialGradient(N / 2, N / 2, 0, N / 2, N / 2, N / 2); bg.addColorStop(0, "#16296e"); bg.addColorStop(0.6, "#0b1647"); bg.addColorStop(1, "#060b2a");
  g.fillStyle = bg; g.fillRect(0, 0, N, N); g.translate(N / 2, N / 2);
  for (let i = 0; i < 900; i++) { const a = hash1(i, 1) * TAU, r = Math.sqrt(hash1(i, 2)) * 64 * k, sz = 0.5 + 2.2 * Math.pow(hash1(i, 3), 6);
    g.fillStyle = `rgba(255,${200 + Math.floor(40 * hash1(i, 4))},${110 + Math.floor(80 * hash1(i, 5))},${0.35 + 0.6 * hash1(i, 6)})`; g.beginPath(); g.arc(r * Math.cos(a), r * Math.sin(a), sz, 0, TAU); g.fill(); }
  g.strokeStyle = "rgba(240,196,96,0.85)";
  for (const pl of PLANETS) { g.lineWidth = 0.14 * k; g.beginPath(); g.arc(0, 0, pl[1] * k, 0, TAU); g.stroke(); }
  g.lineWidth = 0.1 * k; for (let i = 0; i < 360; i += 2) { const a = i * DEG, r0 = (i % 30 === 0 ? 59.5 : i % 10 === 0 ? 61 : 62) * k; g.beginPath(); g.moveTo(r0 * Math.cos(a), r0 * Math.sin(a)); g.lineTo(63.5 * k * Math.cos(a), 63.5 * k * Math.sin(a)); g.stroke(); }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t;
}
function buildOrrery() {
  const root = new THREE.Group(); S.add(root);
  const add = (g, m, parent = root) => { const q = new THREE.Mesh(g, m); parent.add(q); return q; };
  const night = new THREE.MeshStandardMaterial({map: nightTexture(), metalness: 0.55, roughness: 0.32});
  add(centreUV(extrude(new THREE.Shape(arcPts(66, 0, TAU, 128).slice(0, -1)), 1.2, 0.15, -1.2), 132), night);
  { const {pts, rr} = toothOutline(180, 0.78, {pinion: false}); const sh = new THREE.Shape(pts); sh.holes.push(new THREE.Path(arcPts(66.05, 0, TAU, 128).slice(0, -1)));
    add(centreUV(extrude(sh, 1.6, 0.12, -1.4), 150), M.brass); }
  // the sun on its turned pillar, over a stack of wheels: one for each planet
  add(lathe([[4.2, 0], [4.2, 0.4], [2.0, 1.0], [1.3, 6], [1.9, 8.2], [1.2, 8.6], [0.01, 8.6]], 40), M.gold);
  const sun = add(new THREE.SphereGeometry(4.4, 40, 24), new THREE.MeshBasicMaterial({color: 0xffffff})); sun.position.z = 13.4;
  const arms = [];
  PLANETS.forEach((pl, i) => {
    const [name, r, size, period, mat] = pl, g = new THREE.Group(); root.add(g);
    const z = 0.5 + (5 - i) * 0.62, N = 96 - i * 12;
    add(wheelGeo(N, 0.2, 0.3, {spokes: 6, hub: 2.2, bevel: 0.04}), M.brass, g).position.z = z;
    const rod = new THREE.BoxGeometry(r - 2, 0.42, 0.24); rod.translate((r + 2) / 2, 0, z + 0.4); add(rod, M.gold, g);
    const zp = 13.4 - (name === "jupiter" ? 0 : 0) ; add(cyl(0.2, z + 0.4, zp, 10), M.steel, g).position.x = r;
    const body = add(new THREE.SphereGeometry(size, 36, 20), mat === "brass" ? new THREE.MeshStandardMaterial({color: 0xd8a860, metalness: 1, roughness: 0.3, normalMap: TEX.brushed, normalScale: V2(0.8, 0.8)}) : M[mat], g); body.position.set(r, 0, zp);
    if (mat === "brass") { body.rotation.x = Math.PI / 2; body.material.normalMap = TEX.brushed.clone(); body.material.normalMap.repeat.set(1, 3); body.material.normalMap.needsUpdate = true; }
    const a = {g, r, period, body, zp};
    if (name === "saturn") { const ring = new THREE.RingGeometry(size * 1.35, size * 2.15, 64); const rm = add(ring, new THREE.MeshStandardMaterial({color: 0xf0c890, metalness: 1, roughness: 0.3, side: THREE.DoubleSide}), g); rm.position.set(r, 0, zp); rm.rotation.set(0.42, 0.18, 0); }
    if (name === "earth") { const mg = new THREE.Group(); mg.position.set(r, 0, zp); g.add(mg); const moon = add(new THREE.SphereGeometry(0.48, 20, 12), M.steel, mg); moon.position.x = 3.3; const mr = new THREE.BoxGeometry(3.3, 0.12, 0.12); mr.translate(1.65, 0, -0.9); add(mr, M.gold, mg); add(cyl(0.07, -0.9, 0, 6), M.gold, mg).position.x = 3.3; a.moon = mg; }
    arms.push(a);
  });
  const light = new THREE.PointLight(0xffd9a0, 420, 0, 1.5); light.position.set(0, 0, 13.4); S.add(light);
  const update = (W, sunAmt = 1) => {
    arms.forEach((a, i) => { a.g.rotation.z = 0.7 + i * 2.1 + TAU * W / (a.period * YEAR); if (a.moon) a.moon.rotation.z = TAU * W / (YEAR / 12.37); });
    sun.material.color.setRGB(3.6 * sunAmt, 2.4 * sunAmt, 0.9 * sunAmt); light.intensity = 420 * sunAmt;
  };
  return {root, update, sun, arms};
}
STUDIO.night = () => makeEnv([
  [[-0.5, 0.62, 0.6], [1, 0, 0], 0.5, 0.36, 0.42, 0.3, 0xa8c0ff, 1.1],
  [[0.86, -0.15, 0.48], [0, 1, 0], 0.1, 0.9, 0.06, 0, 0x7090ff, 1.6],
  [[-0.2, -0.92, 0.33], [1, 0, 0], 1.1, 0.08, 0.06, 0, 0xffc890, 1.2],
  [[0.5, 0.42, 0.76], [1, 0, 0], 0.03, 0.03, 0.015, 0, 0xffffff, 14],
  [[0.1, -0.1, 1], [1, 0, 0], 0.9, 0.9, 0.8, 0.5, 0x8098e0, 0.2],
], hx(0x05070f, 1), hx(0x030308, 1));
// the orrery's own time: it runs with the song until bar 56, then only as fast as the faltering ticks
const orreryTime = (T) => T < 56 * BAR ? T : 56 * BAR + (beat(T) - beat(56 * BAR)) * BEAT;
function orreryWorld() {
  S.environment = STUDIO.night(); S.background = hx(0x010103);
  O.or = buildOrrery(); O.fl = makeFlares(8);
  O.dust = makeDust(320, [260, 260, 120, 0, 0, 10], 0.9, 5);
  C.near = 2; C.far = 600;
}
MODES.orrery = {
  build() { orreryWorld(); },
  frame(T, t) {
    const u = t / (8 * BAR), W = orreryTime(T);
    O.or.update(W, 1 + 0.12 * noteEnv("box", T, 0.8));
    const az = -1.9 + 0.9 * ease(u), el = mix(0.16, 0.5, ease(u)), dist = mix(52, 112, ease(u));
    const d = setCam(dist * Math.cos(el) * Math.cos(az), dist * Math.cos(el) * Math.sin(az), 9 + dist * Math.sin(el), 0, 0, 9, 0, 36, [0, 0, 1]);
    S.environmentIntensity = 1; S.environmentRotation.set(0, 0, 0.3 * t * 0.1);
    updateDust(O.dust, T, hx(0xffe0a0), 0.9, 0.4);
    flare(O.fl, 0, VA.set(0, 0, 13.4), 16, 0.16 + 0.1 * noteEnv("box", T, 1.0), hx(0xffb860));
    const nt = AU.notes.twinkle; if (nt) for (let k = 0; k < 4; k++) { const i = lastIdx(nt.t, T) - k; if (i < 0 || nt.t[i] < 95) { flare(O.fl, 1 + k, VA, 1, 0); continue; }
      const a = hash1(i, 11) * TAU, r = 30 + 30 * hash1(i, 12); flare(O.fl, 1 + k, VA.set(r * Math.cos(a), r * Math.sin(a), 0.4), 5, 0.7 * Math.exp(-(T - nt.t[i]) / 0.8), GOLDC); }
    finish(T, {exp: 1.0, focus: d * 0.86, aperture: 16, maxR: 9, bloom: 0.45, bloomT: 1.0, vig: 0.7, gain: hx(0xeaf0ff), lift: hx(0x03040a), sat: 1.1, flash: 0.1 * Math.exp(-t / 0.7), flashCol: hx(0x4060d0)});
  },
};
// ---- 08 falter (bars 56-60): the tick comes back late, later; the planets slow with it and the sun dims ----
MODES.falter = {
  build() { orreryWorld(); },
  frame(T, t) {
    const u = t / (4 * BAR), W = orreryTime(T), tk = tickEnv(T, 0.35), dim = 1 - 0.5 * ease(u);
    O.or.update(W, dim * (0.75 + 0.5 * tk));
    const az = -1.0 + 0.25 * u, el = mix(0.5, 1.1, ease(u)), dist = mix(112, 132, ease(u));
    const d = setCam(dist * Math.cos(el) * Math.cos(az), dist * Math.cos(el) * Math.sin(az), 9 + dist * Math.sin(el), 0, 0, 6, 0, 36, [0, 0, 1]);
    S.environmentIntensity = dim; updateDust(O.dust, T, hx(0xa0b8ff), 0.6 * dim, 0.4 * dim);
    flare(O.fl, 0, VA.set(0, 0, 13.4), 20, (0.15 + 0.25 * tk) * dim, hx(0xffb860));
    finish(T, {exp: 1.0, focus: d, aperture: 6, maxR: 6, bloom: 0.45, bloomT: 1.0, vig: 0.75 + 0.15 * u, gain: lc(hx(0xeaf0ff), hx(0x9fb4ff), u), lift: hx(0x02030a), sat: 1.05 - 0.35 * u, fade: 1 - 0.5 * sstep(3.5 * BAR, 4 * BAR, t)});
  },
};

// ---- 09 build (bars 60-68): back at the movement, cold; it rises and brightens; in bar 67 everything stops ----
MODES.build = {
  build() { watchWorld("cool", 0x020203, 0.8); movementOnly(); O.dust = makeDust(160, [50, 50, 30, 0, 0, 14], 0.22, 9); },
  frame(T, t) {
    const b = t / BAR, stop = b >= 7, u = clamp(b / 7), heat = Math.pow(u, 1.7);
    O.w.update(T, {dial: 0, run: 1});
    const az = -2.2 + 1.5 * ease(b / 8), dist = mix(13, 62, ease(u)), el = mix(0.5, 1.05, ease(u)), bal = CAL.balance, tx = mix(bal.x, 0, ease(u)), ty = mix(bal.y, -0.5, ease(u));
    const d = setCam(tx + dist * Math.cos(el) * Math.cos(az), ty + dist * Math.cos(el) * Math.sin(az), 2.5 + dist * Math.sin(el), tx, ty, 2.5, 0, 34, [0, 0, 1]);
    const tk = env("taiko", T, 0.3), g = O.w.update.glint, hold = stop ? sstep(7.0, 7.2, b) : 0;
    S.environmentIntensity = (1.0 + 0.25 * heat) * (1 + 0.3 * tk) * (1 - 0.72 * hold); O.key.intensity = (0.3 + 0.3 * heat) * (1 - 0.8 * hold);
    envTrack(az, 1.25 - 0.45 * heat - 0.25 * tk);
    updateDust(O.dust, stop ? 14 : T, WARMW, (0.3 + 0.5 * heat) * (1 - 0.6 * hold), 0.5);
    flare(O.fl, 0, O.w.H.three.hit, 3, 0.8 * g.three * (1 - hold), hx(0xff7a50));
    flare(O.fl, 1, O.w.H.four.hit, 3, 0.7 * g.four * (1 - hold), COOLW);
    flare(O.fl, 2, VA.set(bal.x, bal.y, 4.6), 7, stop ? 0.6 * hold * (1 - sstep(7.86, 7.97, b)) : 0, COOLW);
    finish(T, {exp: (1.15 + 0.0 * heat) * (1 + 0.12 * tk), focus: d, aperture: mix(26, 6, u), maxR: 10, bloom: 0.4 + 0.5 * heat, vig: 0.7 + 0.2 * hold, gain: lc(lc(hx(0xd0dcff), hx(0xfff0d8), heat), hx(0x90a8e8), hold),
      lift: hx(0x03040a), sat: (0.8 + 0.25 * heat) * (1 - 0.5 * hold), flash: 0.7 * Math.exp(-t / 0.4) + (stop ? 0.9 * Math.exp(-(t - 7 * BAR) / 0.18) : 0), flashCol: stop ? ONE : COOLW});
  },
};

// ---- 10, 11 climax (bars 68-84): the movement flies apart on the hit, every part still in time; it closes again in the last bar ----
function climaxFrame(T, t) {
  const tc = T - 68 * BAR, b = tc / BAR;
  const open = 1 - Math.exp(-tc / 0.3) * Math.cos(tc * 5.2), close = ease((b - 15) / 0.97);
  const e = (b < 15 ? open : 1 - close) * (1 + 0.03 * env("taiko", T, 0.25));
  O.w.update(T, {dial: 1, explode: e});
  // a slow turn round the stack, rising from the plate to the dial; twice it comes in close
  const u = b / 16, az = -2.35 + 2.5 * u, el = 0.36 + 0.2 * ease(u) + 0.3 * close + 0.07 * Math.sin(u * TAU * 2), near = Math.pow(0.5 - 0.5 * Math.cos(u * TAU * 2), 2);
  const dist = mix(mix(76, 50, near), 80, close), tz = mix(2.5, mix(3.5, 0 + 9 * u, near * 0.8), e), side = 7 * near * Math.sin(u * TAU);
  const d = setCam(side + dist * Math.cos(el) * Math.cos(az), dist * Math.cos(el) * Math.sin(az), tz + dist * Math.sin(el), side * 0.6, 0, tz, 0, 31, [0, 0, 1]);
  const tk = env("taiko", T, 0.35), bm = env("boom", T, 0.9), ch = noteEnv("chime", T, 1.0), L = O.w.L;
  const calm = sstep(8, 9.5, b);                              // in the second half the camera comes closer: less bloom, the soft box kept further from the mirror
  S.environmentIntensity = 1.4 * (1 + 0.16 * tk + 0.12 * bm); O.key.intensity = 0.4 + 0.12 * tk; envTrack(az, 1.4 + 0.2 * calm - (0.3 - 0.12 * calm) * tk - (0.2 - 0.08 * calm) * bm);
  updateDust(O.dust, T, GOLDC, 0.7 + 0.5 * tk, 1.0);
  const tick = tickEnv(T, 0.1);
  [[CAL.centre, L.bridge], [CAL.third, L.bridge], [CAL.fourth, L.bridge], [CAL.escape, L.lowbridge], [CAL.pallet, L.lowbridge], [CAL.balance, L.cock]].forEach(([p, lay], i) =>
    flare(O.fl, i, VA.set(p.x, p.y, lay.position.z + (lay === L.cock ? 4.6 : 3.1)), 4.5, (0.45 * tick + 0.7 * ch) * e, i % 2 ? RUBYC : GOLDC));
  flare(O.fl, 7, VA.copy(O.w.H.chime.hit).setZ(L.poly.position.z + 1.6), 8, 1.0 * ch * e, GOLDC);
  finish(T, {exp: 1.08 + 0.06 * tk, focus: d * (1 - 0.1 * near), aperture: 7 + 9 * near, maxR: 8, bloom: 0.6 - 0.2 * calm, bloomT: 0.95 + 0.3 * calm, vig: 0.62, gain: hx(0xfff0d6), lift: hx(0x04050c), sat: 1.12,
    flash: 0.7 * Math.exp(-tc / 0.2) + 0.12 * (b >= 8 ? Math.exp(-(tc - 8 * BAR) / 0.4) : 0) + 0.7 * Math.pow(clamp((b - 15.7) / 0.3), 3), flashCol: WARMW});
}
MODES.climax1 = { build() { watchWorld("warm", 0x030305, 0.45); movementOnly(); O.w.L.hands.visible = true; M.dial.color.setScalar(0.62); O.dust = makeDust(260, [150, 150, 80, 0, 0, 10], 0.7, 13); }, frame: climaxFrame };
MODES.climax2 = MODES.climax1;

// ---- 12 coda (bars 84-94 and the last chord): the watch whole again, further and further away; the end card ----
MODES.coda = {
  build() { watchWorld("warm", 0x020202, 0.5); },
  frame(T, t) {
    O.w.update(T, {});
    const L = 10 * BAR, END = L + 3, u = t / END, card = sstep(4 * BAR, 5.4 * BAR, t), out = 1 - sstep(END - 2.4, END - 0.3, t);
    const c = glide([5, -24, 58, 3, 0, 3], [36, -34, 118, 31, -2, 0], Math.pow(u, 0.6));
    const d = setCam(c[0], c[1], c[2], c[3], c[4], c[5], 0, 30, [0, 0.35, 1]);
    pulse(T, 1.0 - 0.35 * card, 0.3); S.environmentRotation.set(0, 0, -0.3 + 0.5 * u);
    const ch = noteEnv("chime", T, 1.6) * (t > 7);
    flare(O.fl, 0, VA.set(-6, 12, 8), 14, 0.7 * ch, GOLDC);
    flare(O.fl, 1, VA.set(0, -8.3, 6.2), 4, 0.5 * tickEnv(T, 0.1), WARMW);
    finish(T, {exp: 1.0 - 0.2 * card, focus: d, aperture: 12, maxR: 7, bloom: 0.5, vig: 0.7, gain: lc(hx(0xfff4e4), hx(0xffe6c8), u), lift: hx(0x040302), fade: out, flash: 1.3 * Math.exp(-t / 0.5), flashCol: WARMW});
    const a = card * out;
    endEl.style.opacity = a.toFixed(3); endEl.style.display = a > 0.002 ? "block" : "none";
  },
};

// ====================================================================================================
function makeText(serif, sans, mono) {
  const css = document.createElement("style");
  css.textContent = `
    .es-card{position:absolute;left:0;top:0;width:100vw;height:100vh;display:none;pointer-events:none;color:#f3ede2}
    .es-title{position:absolute;left:5.5vw;top:37vh;font-family:${serif};font-weight:500;font-size:3.9vw;letter-spacing:.26em;white-space:nowrap;text-shadow:0 0 1.4vw rgba(150,180,255,.35)}
    .es-rule{position:absolute;left:5.7vw;width:9vw;top:49.6vh;height:1px;background:linear-gradient(90deg,#d9b46a,rgba(217,180,106,0))}
    .es-sub{position:absolute;left:5.7vw;top:52.6vh;font-family:${sans};font-size:1.15vw;letter-spacing:.42em;text-transform:uppercase;color:#aab4c8;white-space:nowrap}
    .es-end{text-align:left}
    .es-end .es-title{left:51vw;top:27.5vh;font-size:2.7vw;letter-spacing:.3em;text-shadow:0 0 1.2vw rgba(255,200,120,.3)}
    .es-end .es-rule{left:51.2vw;top:36.6vh;width:9vw}
    .es-end .es-sub{left:51.2vw;top:40.2vh;color:#c9bda9}
    .es-url{position:absolute;left:51.2vw;top:45.4vh;font-family:${mono};font-size:1.22vw;letter-spacing:.01em;color:#fff3df;white-space:nowrap}
    .es-line{position:absolute;left:51.2vw;top:55vh;font-family:${serif};font-style:italic;font-size:1.5vw;color:#d8ccb8;white-space:nowrap}
    .es-line2{top:59.4vh}`;
  document.head.append(css);
  const el = (cls, text, parent) => { const d = document.createElement("div"); d.className = cls; if (text) d.textContent = text; parent.append(d); return d; };
  titleEl = el("es-card", "", document.body); titleEl.dataset.vidgenId = "title-card"; titleEl.dataset.vidgenLint = "off";
  el("es-title", "ESCAPEMENT", titleEl); el("es-rule", "", titleEl); el("es-sub", "a clockwork film in D minor", titleEl);
  endEl = el("es-card es-end", "", document.body); endEl.dataset.vidgenId = "end-card"; endEl.dataset.vidgenLint = "off";
  el("es-title", "ESCAPEMENT", endEl); el("es-rule", "", endEl); el("es-sub", "made with schu-video-generator", endEl);
  el("es-url", "https://github.com/joaopauloschuler/schu-video-generator", endEl);
  el("es-line", "Every wheel turns at the speed its teeth give it.", endEl); el("es-line es-line2", "The score is played by the generator's own synthesizer.", endEl);
}

export async function load(ctx) {
  Q = ctx.data.q || {}; mode = ctx.data.mode; t0 = ctx.music.t0; W = ctx.width; H = ctx.height;
  AU = fromMusic(ctx.music);
  document.documentElement.style.background = "#000"; document.body.style.background = "#000"; document.body.style.margin = "0"; document.body.style.overflow = "hidden";
  R = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false, powerPreference: "high-performance"});
  R.setPixelRatio(1); R.setSize(W, H, false); R.setClearColor(0x000000, 1); R.toneMapping = THREE.NoToneMapping;
  R.shadowMap.enabled = Q.shadow ?? true; R.shadowMap.autoUpdate = false; R.shadowMap.type = THREE.PCFShadowMap;
  PM = new THREE.PMREMGenerator(R);
  S = new THREE.Scene();
  C = new THREE.PerspectiveCamera(30, W / H, 1, 400);
  const serif = `"${ctx.theme.fonts.serif}", Georgia, serif`;
  try { await document.fonts.load(`600 40px "${ctx.theme.fonts.serif}"`); await document.fonts.load(`italic 500 40px "${ctx.theme.fonts.serif}"`); } catch (e) { /* the fallback serif is used */ }
  makeTextures(serif); makeMaterials(); makeText(serif, `"${ctx.theme.fonts.body}", sans-serif`, `"${ctx.theme.fonts.mono}", monospace`);
  MODES[mode].build();
  composer = new EffectComposer(R, new THREE.WebGLRenderTarget(W, H, {type: THREE.HalfFloatType}));
  scenePass = new ScenePass(W, H); composer.addPass(scenePass);
  bloom = new UnrealBloomPass(V2(W >> (Q.bloomHalf ?? 2), H >> (Q.bloomHalf ?? 2)), 0.35, 0.5, 1.0); if (Q.bloom ?? true) composer.addPass(bloom);
  fin = new ShaderPass(FIN); fin.uniforms.uRes.value.set(W, H); composer.addPass(fin);
  aa = new ShaderPass(AA); aa.uniforms.uRes.value.set(W, H); composer.addPass(aa);
  MODES[mode].frame(t0, 0); composer.render();          // compile every shader now, not on the first frame
  { const gl = R.getContext(); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(4)); }
}

export function frame(t, ctx) {
  const T = t0 + t;
  MODES[mode].frame(T, t);
  if (Q.info) {
    const gl = R.getContext(), tm = {}; let t1 = performance.now();
    for (const p of composer.passes) { if (!p._r) { p._r = p.render; p.render = function (...a) { gl.finish(); const q = performance.now(); p._r.apply(p, a); gl.finish(); p._ms = performance.now() - q; }; } }
    composer.render(); gl.finish();
    composer.passes.forEach((p, i) => { tm[p.constructor.name + i] = Math.round(p._ms); });
    document.title = JSON.stringify({tri: R.info.render.triangles, calls: R.info.render.calls, total: Math.round(performance.now() - t1), ...tm});
  } else composer.render();
}
