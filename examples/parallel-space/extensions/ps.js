// Parallel Space (v8): one three.js module for every scene of the music video (data.mode picks the set).
//
// Everything is a function of the song time T = ctx.music.t0 + t on a grid of 52 frames per bar
// (138.46 BPM at 30 fps): no state is carried from frame to frame or from scene to scene, and
// every "random" number comes from a seeded generator, so a scene renders the same every time,
// in any order. The pictures follow the music through ctx.music (video.yaml: `music_data`):
// spectrum bands and level measured from the mix, and the score's own notes (kick, big drums,
// booms, ticks, every note of the hook with its pitch).
//
// The look: light on black. The building blocks are vidgen's "vidgen/three-kit" (glowing strokes,
// glass crystals, the tesseract, the nebula sky, portals, star fields, flares, shock rings, the
// melody's ribbon, the spectrum's rays, the corridor, the great rings) and "vidgen/music-time"
// (envelopes of the score's hits and notes, seeded numbers, easing); this file composes them into
// scenes and finishes the frame with bloom, a filmic tone curve, a colour grade per section, a
// slight chromatic fringe, a vignette and fine grain.
//
// Rules kept from the owner's notes on earlier versions: the kick pulses the BRIGHTNESS of
// objects, never the zoom; rotations are smooth (no beat flicks); nothing large sweeps through
// the camera as stripes (segments are cut at the near plane and wrapped objects fade in far away).
import * as THREE from "three";
import {EffectComposer} from "three/addons/postprocessing/EffectComposer.js";
import {RenderPass} from "three/addons/postprocessing/RenderPass.js";
import {UnrealBloomPass} from "three/addons/postprocessing/UnrealBloomPass.js";
import {ShaderPass} from "three/addons/postprocessing/ShaderPass.js";
import {clamp, mix, smoothstep, smootherstep, rng, hash, count, barClock, trackArrays, lastIndex, hitEnvelope, noteLevel, melody} from "vidgen/music-time";
import {setStage, color, mixColor, Glow, circleSegments, polyhedronEdges, POLYHEDRA, makeCrystal, lightCrystal, SkyDome, makePortal, lightPortal, lightDial,
  TESSERACT_VERTICES, TESSERACT_EDGES, project4, tesseractAngles, makeTesseract, updateTesseract, wrapZ, makeStarField, updateStarField, makeStarShell,
  makeFlare, setFlare, makeShockRings, updateShockRings, updateGlints, makeRibbon, updateRibbon, makeSpectrumRays, updateSpectrumRays, updateTunnel,
  makeLattice, updateLattice, makeRingStructure, updateRingStructure, makeCrystalField, updateCrystalField, makeCrystalSwarm, updateCrystalSwarm, aimCamera} from "vidgen/three-kit";
import {titleCard, endCard} from "vidgen/title-cards";

const {bar: BAR, beat: BEAT, sixteenth: S16} = barClock(52 / 30), TAU = Math.PI * 2;
let R, S, C, composer, bloom, fin, W, H, AU, mode, t0;
let card;                                       // the opening title (dawn) or the end card (coda): vidgen/title-cards
// the opening and the end card frame the one light off centre: in the right third under the title, in the left third
// under the end card (the title block takes the other third). SIDE is tan(the angle off the axis), so the light stays
// in its third while the camera moves: about 23 degrees, a little over half way out in a 50-degree, 16:9 frame
// (the light's centre near 76 % of the width in the opening, 24 % at the end).
const SIDE = 0.43;
const O = {};
const uRes = {value: new THREE.Vector2(1280, 720)};

// colours (sRGB hex; three.js converts them to linear light)
const ICE = color(0x9fdcff), CYAN = color(0x35e8ff), TEAL = color(0x1fd0c0), BLUE = color(0x3f6bff), INDIGO = color(0x5a48ff), VIO = color(0x9b5cff),
  MAG = color(0xff3fb4), ROSE = color(0xff7aa8), AMBER = color(0xffa63c), GOLD = color(0xffd166), ORANGE = color(0xff6a2a), EMBER = color(0xff3a24),
  WHITE = color(0xfff4e6), GREEN = color(0x5dffb0);

// ---------- the music as data ----------
// vidgen hands the page the music (video.yaml: `music_data`): the mix measured per frame (level, 16
// spectrum bands) and the score's events, read here into sorted arrays per track: when each drum is
// struck (t, gain) and every note (t, length, pitch). "call" gathers the far choir (the track named
// trumpet) and the violas on the hook (the track named violins). Times are kept on the score's grid of
// sixteenths to three decimals (`grid`), as the film's own exporter wrote them before `music_data`.
const HIT_TRACKS = ["kick", "taiko", "tom", "boom", "clap", "snare", "crash", "tick", "roll", "frame"];
const NOTE_TRACKS = {hook: ["hook"], lead: ["lead"], call: ["trumpet", "violins"], horn: ["horn"], swell: ["swell"]};
let M;
const level = (T) => M.level(T);
const band = (T, b) => M.band(b, T);
const kick = (T) => hitEnvelope(AU.hits.kick, T, 0.1);
const V3 = new THREE.Vector3(), V3b = new THREE.Vector3();

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

// ====================================================================================================
// the scenes
// ====================================================================================================
const MODES = {};

// ---- dawn (bars 0-8): one small light in a very large dark, in the right third; the title in the left third, on
//      calm dark space; a far men's choir lights stars around the light, then a clock starts ----
MODES.dawn = {
  build() {
    O.sky = new SkyDome(3);
    O.stars = makeStarField(900, [14, 260], 620, 11);
    O.dust = makeStarField(160, [3, 40], 160, 29, {px: 3.2, tints: [ICE, BLUE, WHITE]});
    O.tes = makeTesseract({world: 0.05}); O.tes.position.set(0, 0, -150); O.tes.scale.setScalar(6.5);
    O.flare = makeFlare(1, {streak: 1.0, rays: 0.3}); O.flare.position.copy(O.tes.position);
    O.shocks = makeShockRings(3);
    O.glints = new Glow(60, {px: 1.6, halo: 1.6, haloGain: 0.5});
    const marks = []; for (let i = 0; i < 16; i++) { const a = (i / 16) * TAU; marks.push(Math.sin(a) * 15, Math.cos(a) * 15, 0, Math.sin(a) * (i % 4 ? 16.2 : 17.4), Math.cos(a) * (i % 4 ? 16.2 : 17.4), 0); }
    O.dial = Glow.from(marks, {px: 1.3, world: 0.12}); O.dial.mesh.position.copy(O.tes.position);
  },
  frame(T, t) {
    const p = clamp(t / (8 * BAR)), boom = hitEnvelope(AU.hits.boom, T, 1.4), horn = noteLevel(AU.notes.horn, T, 0.5, 1.2);
    const cz = -62 * smootherstep(p * 0.96);
    const cx = Math.sin(T * 0.11) * 2.4;
    aimCamera(cx, 1.0 + Math.cos(T * 0.09) * 1.2, cz, cx - SIDE * (150 + cz), 0, -150, 0.03 * Math.sin(T * 0.13), 50);     // the light in the right third
    O.sky.turn(T);
    card.update(t);
    const calm = smoothstep(0.5 * BAR, 3 * BAR, t);                                                                         // the sky quieter from the title on, to the cut
    O.sky.colors(color(0x010207), color(0x051a33), mixColor(color(0x1c6a8c), color(0x4a8a9a), horn), (0.32 + 0.2 * p) * (1 - 0.32 * calm));
    O.sky.light(1, V3.set(0.05, 0.02, -1), mixColor(ICE, AMBER, horn * 0.5), 0.03 + 0.10 * boom + 0.05 * horn, 14);
    O.sky.light(2, V3.set(0.7, 0.45, -0.4), BLUE, 0.02 + 0.02 * p, 3);                                                     // to the right, away from the title
    updateStarField(O.stars, T, 6 * t, 0.0, cz, 1);
    updateStarField(O.dust, T, 3 * t, 0.0, cz, 0.12, 4);
    updateTesseract(O.tes, tesseractAngles(T * 0.35 + 2), mixColor(ICE, WHITE, boom), 1.1 + 2.2 * boom + 0.5 * horn, 2.2 + 3 * boom);
    setFlare(O.flare, mixColor(ICE, AMBER, horn * 0.6), 0.5 + 1.6 * boom + 0.6 * horn, T * 0.05, 26 + 10 * boom);
    updateShockRings(O.shocks, AU.hits.boom, T, ICE, {at: O.tes.position, r0: 6, r1: 48, life: 6, gain: 2.2 * (1 - 0.7 * calm), face: true});   // they stay near the light
    // a clock around the light: every tick lights the next mark
    const ticks = AU.hits.tick, ti = lastIndex(ticks.t, T), te = hitEnvelope(AU.hits.tick, T, 0.22);
    for (let i = 0; i < 16; i++) { const back = ti < 0 ? 99 : ((ti - i) % 16 + 16) % 16; O.dial.col(i, ICE, ti < 0 ? 0 : 0.18 + (back < 5 ? te * Math.pow(0.5, back) * 3.2 : 0)); }
    O.dial.flush(false, true); O.dial.mesh.quaternion.copy(C.quaternion);
    // every note of the far choir (the track named trumpet) lights a star for a while, higher notes higher up
    // (v7 sings it two octaves under v6's trumpet: 46 here was 70, so the stars stay where they were); v8: only on
    // the light's side and around it, never under the title
    const bells = AU.notes.call, bi = lastIndex(bells.t, T);
    for (let k = 0; k < 12; k++) {
      const j = bi - k, base = k * 5;
      if (j < 0 || T - bells.t[j] > 5) { for (let q = 0; q < 5; q++) O.glints.hide(base + q); continue; }
      const age = T - bells.t[j], e = Math.exp(-age / 1.6) * clamp(age / 0.08), a = (hash(j, 1) - 0.5) * 3.9, rr = 26 + 30 * hash(j, 2);
      const x = Math.cos(a) * rr * 1.5, y = (bells.p[j] - 46) * 2.6 + Math.sin(a) * 8, z = -150 + 30 * (hash(j, 3) - 0.5), s = 2.2 * e + 0.4;
      O.glints.dot(base, x, y, z); O.glints.col(base, WHITE, 5 * e, 2.4);
      O.glints.seg(base + 1, x - s * 2, y, z, x + s * 2, y, z); O.glints.seg(base + 2, x, y - s, z, x, y + s, z);
      O.glints.seg(base + 3, x - s * 0.5, y - s * 0.5, z, x + s * 0.5, y + s * 0.5, z); O.glints.seg(base + 4, x - s * 0.5, y + s * 0.5, z, x + s * 0.5, y - s * 0.5, z);
      for (let q = 1; q < 5; q++) O.glints.col(base + q, ICE, (q < 3 ? 1.6 : 0.7) * e, 0.7);
    }
    O.glints.flush();
    finish(T, {exp: 1.0, bloom: 0.7, fade: smoothstep(0, 2.2, t), flash: 0, lift: color(0x020409), gain: new THREE.Color(0.96, 1.0, 1.06), vig: 0.7});
  },
};

// the ostinato's sixteenths: 1 on an accent of its 3+3+2 figure, less on the notes between
const OST_ACC = [1, 0.3, 0.3, 1, 0.3, 0.3, 1, 0.3, 1, 0.3, 0.3, 1, 0.3, 0.3, 1, 0.3];
function ostEnv(T, decay = 0.07) { if (T < 0) return 0; const k = count(T, S16); return OST_ACC[k % 16] * Math.exp(-(T - k * S16) / decay); }

// ---- pulse (bars 8-24): the ostinato; a corridor of cells lights up note by note, then opens onto great rings ----
MODES.pulse = {
  build() {
    O.sky = new SkyDome(7);
    O.stars = makeStarField(900, [24, 300], 700, 13);
    O.dust = makeStarField(180, [2.5, 30], 150, 31, {px: 3.0, tints: [ICE, BLUE, WHITE]});
    O.lat = makeLattice(14, 22, 11);
    O.rings = makeRingStructure();
    O.tes = makeTesseract({world: 0.05}); O.rings.g.add(O.tes); O.tes.scale.setScalar(8);
    O.flare = makeFlare(1, {streak: 1.2, rays: 0.5});
    O.shocks = makeShockRings(3, 128);
  },
  frame(T, t) {
    const tt = T - 8 * BAR, L = 16 * BAR, p = clamp(tt / L);
    const dist = 26 * tt + 25 * tt * tt / L, D = (26 * L + 25 * L) - dist + 6;             // distance to the rings' centre
    const k = kick(T), taiko = hitEnvelope(AU.hits.taiko, T, 0.45), boom = hitEnvelope(AU.hits.boom, T, 1.2), horn = noteLevel(AU.notes.horn, T, 0.5, 1.0), swell = smoothstep(0.5, 1, p), lv = level(T);
    const open = smoothstep(0.44, 0.6, p), rise = Math.sin(Math.PI * smoothstep(0.47, 0.97, p));                  // out of the corridor, up, and down again
    const cy = 1.2 * Math.sin(T * 0.21) + 46 * rise, cx = 1.6 * Math.sin(T * 0.17) + 20 * rise;
    O.rings.g.position.set(0, 0, -D);
    aimCamera(cx, cy, 0, cx * 0.3, cy * 0.25, -Math.max(D, 60), 0.05 * Math.sin(T * 0.19) + 0.12 * rise, 56 + 6 * swell);
    O.sky.turn(T);
    O.sky.colors(color(0x010209), color(0x08133c), mixColor(color(0x2a48b8), color(0x5a58c8), swell), 0.3 + 0.25 * swell + 0.1 * lv);
    O.sky.light(1, V3.set(0, 0, -1), mixColor(ICE, AMBER, swell), 0.03 + 0.10 * swell + 0.08 * horn + 0.1 * boom, 9);
    const th = AU.hits.taiko, ti = lastIndex(th.t, T);
    O.sky.light(2, V3.set(Math.cos(ti * 2.4) * 0.8, Math.sin(ti * 1.7) * 0.5, -0.7), mixColor(VIO, ICE, hash(ti)), 0.22 * taiko, 5);
    updateStarField(O.stars, T, dist * 0.5, 0.2 + 2.2 * p * p, 0, 1);
    updateStarField(O.dust, T, dist * 0.8, 0.3 + 1.5 * p, 0, 0.12, 3);
    // the corridor: light runs down it with every note of the ostinato (later cells light later)
    const og = smoothstep(0, 0.25, p) * 0.9 + 0.5;
    updateLattice(O.lat, T, dist, 0, mixColor(BLUE, ICE, 0.35 + 0.4 * p), (i, ahead) => (1 - open) * (0.16 + 0.12 * p + og * 2.2 * ostEnv(tt - ahead / 420) + 1.2 * taiko * Math.exp(-ahead / 90)));
    O.lat.gl.mesh.visible = open < 0.999;
    // the rings: far and small at first, then enormous
    const far = smoothstep(1500, 500, D);
    updateRingStructure(O.rings, T, (q) => mixColor(q % 2 ? ICE : BLUE, AMBER, swell * (q === 0 ? 0.8 : 0.35)), (q) => (0.35 + 0.5 * far + 0.5 * swell) * (1 + 1.2 * k) * (1 + 0.6 * taiko) * (q === 0 ? 1.3 : 1));
    updateTesseract(O.tes, tesseractAngles(T * 0.4 + 5), mixColor(ICE, GOLD, swell), 1.4 + 1.5 * k + taiko, 3 + 2 * k);
    O.flare.position.copy(O.rings.g.position);
    setFlare(O.flare, mixColor(ICE, AMBER, swell * 0.8), 0.45 + 0.5 * swell + 0.4 * horn + 0.8 * boom + 0.5 * k, T * 0.04, 30 + 26 * swell + D * 0.05);
    updateShockRings(O.shocks, AU.hits.boom, T, mixColor(ICE, AMBER, swell), {at: O.rings.g.position, r0: 10, r1: 330, life: 5, gain: 2.5, face: true});
    const cres = smoothstep(15 * BAR, 16 * BAR, tt);
    finish(T, {exp: 1.0 + 0.15 * swell + 0.25 * cres * cres, bloom: 0.6 + 0.15 * swell, flash: 0.8 * Math.exp(-tt / 0.35) + 0.4 * hitEnvelope(AU.hits.boom, T, 0.3) * smoothstep(0.2, 0.6, p) + 1.2 * Math.pow(cres, 8),
      flashCol: mixColor(ICE, WHITE, 0.5), lift: color(0x020309), gain: new THREE.Color(0.97, 1.0, 1.05), vig: 0.65});
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
function gateAge(T) { const k = count(T, S16); for (let back = 0; back < 16; back++) { const j = k - back; if (GATE_STEPS.includes(((j % 16) + 16) % 16)) return {age: T - j * S16, acc: ((j % 16) + 16) % 16 === 0 || ((j % 16) + 16) % 16 === 8 ? 1 : 0.7}; } return {age: 9, acc: 0}; }
// the age of the latest kick (and its number) at song time T
function kickAge(T) { const h = AU.hits.kick, j = h ? lastIndex(h.t, T) : -1; return j < 0 ? {age: 99, j: -1, g: 0} : {age: T - h.t[j], j, g: h.g[j]}; }
// the inner light of the solids: a swell on every chord (two bars each), the choir's notes where it sings, the middle of the spectrum
function innerLight(T) {
  const c = 2 * BAR, age = T - count(T, c) * c;
  return 0.3 + 0.75 * smoothstep(0, 0.9, age) * Math.exp(-age / 2.6) + 1.3 * noteLevel(AU.notes.call, T, 0.3, 1.2) + 0.5 * band(T, 7);
}
// one wireframe solid's edges into a Glow, from index i; returns the next free index
function mcSolid(gl, i, s, Tk, pos, scale, c, m, w = 1) {
  if (s.kind === "tes") {
    const P = s.P, angs = tesseractAngles(Tk * 0.45 + s.ph);
    TESSERACT_VERTICES.forEach((v, q) => project4(v, angs, 3.1, P[q]));
    for (const e of TESSERACT_EDGES) {
      const a = P[e[0]], b = P[e[1]], size = (Math.hypot(a[0], a[1], a[2]) + Math.hypot(b[0], b[1], b[2])) * 0.5;
      gl.seg(i, pos.x + a[0] * scale, pos.y + a[1] * scale, pos.z + a[2] * scale, pos.x + b[0] * scale, pos.y + b[1] * scale, pos.z + b[2] * scale);
      gl.col(i++, c, m * (0.35 + 0.65 * smoothstep(1.1, 2.4, size)), w);
    }
    return i;
  }
  MC_M.makeRotationFromEuler(MC_E.set(Tk * s.spin + s.ph, Tk * s.spin * 1.35, s.ph)).scale(MC_V.set(scale, scale, scale)).setPosition(pos);
  const E = polyhedronEdges(s.kind), el = MC_M.elements;
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
  const out = [], ico = polyhedronEdges("ico"), dod = polyhedronEdges("dodeca"), k = 1 / 0.95;
  for (let q = 0; q < ico.length; q += 6) out.push(ico.slice(q, q + 6));
  for (let q = 0; q < dod.length; q += 6) out.push(dod.slice(q, q + 6).map((v) => v * 0.78 * k));
  const P = TESSERACT_VERTICES.map((v) => project4(v, [0.4, 0.3, 0.2, 0.1, 0.5, 0.3], 3.1, [0, 0, 0]).map((u) => u * 0.2));
  for (const e of TESSERACT_EDGES) out.push([...P[e[0]], ...P[e[1]]]);
  return out;
}
MODES.groove1 = {
  build() {
    O.sky = new SkyDome(12);
    O.stars = makeStarField(800, [22, 240], 520, 17, {tints: [WHITE, ICE, CYAN, VIO]});
    const r = rng(77);
    O.solids = [];
    for (let i = 0; i < 14; i++) {
      const kind = i < 12 ? MC_KINDS[i] : "tes", lane = (i % 7) / 6 - 0.5;
      const hero = i % 4 === 1, side = i % 2 ? 1 : -1;                                      // every fourth solid is a big one, off the flight path
      O.solids.push({kind, x: hero ? side * (6 + 3 * r()) : lane * 2 * (MC.a - 3.6) + (r() - 0.5) * 2.2, y: hero ? (r() - 0.5) * 14 + 4 * side : (r() - 0.5) * 26, z0: (i / 14) * MC.depth + r() * 12,
        s: kind === "tes" ? 1.0 + 0.4 * r() : hero ? 3.0 + 1.2 * r() : 1.1 + 1.2 * r(),
        spin: (0.18 + 0.35 * r()) * (r() < 0.5 ? -1 : 1), ph: r() * TAU, pal: Math.floor(r() * 2), P: TESSERACT_VERTICES.map(() => [0, 0, 0]), sx: r() * 2 - 1, sy: r() * 2 - 1});
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
    const L = 8 * BAR, p = clamp(t / L), lv = level(T), clap = hitEnvelope(AU.hits.clap, T, 0.14);
    const fold = smootherstep(clamp((t - 6 * BAR) / (1.75 * BAR))), open = 1 - fold, calm = 1 - smootherstep(clamp((t - 5.5 * BAR) / (2 * BAR)));
    const dist = MC.v * t;
    // a slow, smooth sway down the middle; still at the end, looking at the solid
    const yaw = Math.sin(TAU * t / (11 * BAR) - 0.6);                                  // we look into one mirror, then the other
    aimCamera(-4.5 * yaw * calm + Math.sin(T * 0.31) * 0.8 * calm, 0.6 + Math.cos(T * 0.27) * 1.2 * calm, 0, 30 * yaw * calm, 0.3 * Math.sin(T * 0.23) * calm, -100, (0.05 * Math.sin(T * 0.17) - 0.04 * yaw) * calm, 64);
    O.sky.turn(T, 2);
    O.sky.colors(color(0x02010c), color(0x150a48), color(0x2a7fd0), 0.34 + 0.12 * lv);
    O.sky.light(1, V3.set(0, 0, -1), mixColor(CYAN, MAG, clap * 0.6), 0.07 + 0.1 * clap + 0.08 * fold, 8);
    O.sky.light(2, V3.set(0.7, 0.4, -0.5), VIO, 0.04, 3);
    updateStarField(O.stars, T, dist * 1.1, 1.4, 0, 1);
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
        const fade = smoothstep(MC.depth, MC.depth * 0.8, dz) * smoothstep(MC.near, MC.near + 10, dz) * (1 - fold);
        const cA = MC_PAL[Math.min(MC_PAL.length - 1, s.pal + ak)], cB = MC_PAL[Math.min(MC_PAL.length - 1, s.pal + ak + 1)];
        const pos = V3b.set(s.x * (1 - 0.6 * fold), s.y * (1 - 0.6 * fold), z);
        const c = mixColor(cA, WHITE, 0.4 * kk), m = fade * (1.25 + 1.9 * kk) * (s.kind === "tes" ? 1.25 : 1);
        if (fade < 0.003) { n++; return; }
        i = mcSolid(gl, i, s, Tk, pos, s.s, c, m, 1);
        // on each kick the solid splits: two copies drift apart from it, fading
        if (ka.age < 1.4 && ka.j >= 0) {
          const e = ka.age, sep = s.s * 1.9 * (1 - Math.exp(-e / 0.24)), gf = Math.exp(-e / 0.42) * Math.min(ka.g, 1.25) * 0.75;
          const an = hash(ka.j * 31 + si, 5) * TAU, ux = Math.cos(an), uy = Math.sin(an) * 0.8;
          const P1 = MC_V.set(pos.x + ux * sep, pos.y + uy * sep, pos.z).clone(), P2 = MC_V.set(pos.x - ux * sep, pos.y - uy * sep, pos.z).clone();
          const cg = mixColor(cB, WHITE, 0.25);
          i = mcSolid(gl, i, s, Tk + 0.15 * e, P1, s.s * 0.92, cg, fade * gf, 0.8);
          i = mcSolid(gl, i, s, Tk - 0.15 * e, P2, s.s * 0.92, cg, fade * gf, 0.8);
        }
        // the light inside it
        const ii = R0.inner;
        ii.dot(n, pos.x, pos.y, pos.z); ii.col(n, mixColor(cA, WHITE, 0.55), fade * inner * (0.42 + 0.5 * kk) * (k === 0 ? 1 : 0.6), s.s * 0.8); n++;
      });
      for (let q = n; q < R0.inner.max; q++) R0.inner.hide(q);
      // dust between the mirrors, moving with the flight
      for (const d of O.dust) {
        const z = wrapZ(d[2], distK * 1.2, MC.depth, 0, 4), dz = -z, f = smoothstep(MC.depth, MC.depth * 0.8, dz) * smoothstep(4, 12, dz) * (1 - fold);
        gl.seg(i, d[0], d[1], z, d[0], d[1], z - 0.9); gl.col(i++, MC_PAL[Math.min(7, 1 + ak)], 0.5 * d[3] * f, 0.8);
      }
      for (let q = i; q < gl.max; q++) gl.hide(q);
      gl.count(i); gl.flush(); R0.inner.flush();
      gl.tint(WHITE, dim); R0.inner.tint(WHITE, dim);
    });
    // ---- the mirrors: seams on every plane (the real ones and their images), flashing with the gate; then they fold into one solid ----
    const tgt = O.target, nT = tgt.length, Dt = mix(46, 92, smootherstep(clamp((t - 6.9 * BAR) / (1.0 * BAR)))), rt = mix(15, 10.5, smootherstep(clamp((t - 6.9 * BAR) / (1.0 * BAR))));
    MC_M.makeRotationFromEuler(MC_E.set(0.35 + T * 0.23, T * 0.31, 0.2 + T * 0.11)).scale(MC_V.set(rt, rt, rt)).setPosition(0, 0.5, -Dt);
    const el = MC_M.elements;
    const tx = (x, y, z, o) => { o[0] = el[0] * x + el[4] * y + el[8] * z + el[12]; o[1] = el[1] * x + el[5] * y + el[9] * z + el[13]; o[2] = el[2] * x + el[6] * y + el[10] * z + el[14]; };
    const A = [0, 0, 0], B = [0, 0, 0], kNow = kick(T), solidC = mixColor(mixColor(ICE, CYAN, 0.3), mixColor(ROSE, GOLD, 0.45), smoothstep(0.55, 1, fold));
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
          g = (0.26 + 1.5 * gEnv + 2.6 * wave) * smoothstep(26 * O.NC, 26 * O.NC * 0.7, ahead) * smoothstep(-6, 8, ahead) * (near < 0.5 ? 1 : 0.35);
        }
        // the fold: every seam flies to an edge of the solid ahead, one after the other
        const u = smootherstep(clamp(fold * 1.7 - (((i * 7) % 61) / 61) * 0.7));
        if (u > 0) {
          const e = tgt[i % nT]; tx(e[0], e[1], e[2], A); tx(e[3], e[4], e[5], B);
          ax = mix(ax, A[0], u); ay = mix(ay, A[1], u); az = mix(az, A[2], u); bx = mix(bx, B[0], u); by = mix(by, B[1], u); bz = mix(bz, B[2], u);
          const dup = Math.ceil(O.seams.max / nT);
          g = mix(g * pg, (i % nT < 30 ? 1.7 : i % nT < 60 ? 1.1 : 0.9) * (1 + 1.5 * kNow) / Math.pow(dup, 0.75), u);
          O.seams.seg(i, ax, ay, az, bx, by, bz); O.seams.col(i, mixColor(pc, solidC, u), g, 1 + 0.5 * u);
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
    setFlare(O.flare, mixColor(ICE, CYAN, 0.5), (0.7 + 0.6 * kNow + 0.4 * lv) * open, T * 0.1, 46);
    O.core.position.set(0, 0.5, -Dt);
    setFlare(O.core, mixColor(ROSE, GOLD, 0.5), smoothstep(0.3, 1, fold) * (0.5 + 0.6 * kNow + 0.4 * innerLight(T)), T * 0.06, 22 + 8 * fold);
    const end = smoothstep(7.55 * BAR, 8 * BAR, t);
    finish(T, {exp: 1.02, bloom: 0.72, flash: 1.0 * Math.exp(-t / 0.3) + 0.45 * Math.pow(end, 4), flashCol: mixColor(mixColor(ICE, WHITE, 0.6), GOLD, end), lift: color(0x02020a), gain: new THREE.Color(0.97, 1.0, 1.06), ca: 0.9});
  },
};

// ---- more shared pieces ----

const ORIGIN = new THREE.Vector3(0, 0, 0);

// a clock: every tick of the score lights the next mark of a dial of 16
function tickDial(dial, T, c, base = 0.18) {
  const ticks = AU.hits.tick, ti = lastIndex(ticks.t, T), te = hitEnvelope(AU.hits.tick, T, 0.22), on = ti >= 0 && T - ticks.t[ti] < 4 ? 1 : 0;
  for (let i = 0; i < 16; i++) { const back = ((ti - i) % 16 + 16) % 16; dial.col(i, c, on * (base + (back < 5 ? te * Math.pow(0.5, back) * 3.2 : 0))); }
  dial.flush(false, true); dial.mesh.quaternion.copy(C.quaternion);
}
// the sun of the drop: a crystal with the tesseract inside, the spectrum as its rays, a ring, the lead as an orbit
function makeSun(o = {}) {
  const g = new THREE.Group(); S.add(g);
  const core = makeCrystal("dodeca", GOLD, ORANGE, {parent: g, world: 0.25, gain: 1.2, base: 0.035, rim: 0.6}); core.scale.setScalar(11);
  const tes = makeTesseract({parent: g, world: 0.12}); tes.scale.setScalar(3.6);
  const spec = makeSpectrumRays(g, o);
  const ring = Glow.from(circleSegments(160, 1), {parent: g, px: 2.4, world: 0.9, halo: 1.8, haloGain: 0.45, max: 9});
  const ring2 = Glow.from(circleSegments(160, 1), {parent: g, px: 1.0, world: 0.2, halo: 1.2, haloGain: 0.3});
  const rib = makeRibbon(200, {parent: g, world: 0.8, px: 2.0, max: 8});
  const flare = makeFlare(1, {streak: 1.5, rays: 0.6});
  return {g, core, tes, spec, ring, ring2, rib, flare};
}
// o: {k (kick 0..1), cA, cB (spectrum), cR (ring), r0, len, R (ring radius), gain, lead: [centre pitch], flare, flareC, flareS}
function updateSun(sun, T, o) {
  const k = o.k ?? 0, g = o.gain ?? 1;
  sun.core.rotation.set(T * 0.11, T * 0.17, 0); lightCrystal(sun.core, k, g);
  updateTesseract(sun.tes, tesseractAngles(T * 0.5), mixColor(GOLD, WHITE, 0.4 + 0.6 * k), (1.0 + 1.2 * k) * g, (2.2 + 2 * k) * g);
  updateSpectrumRays(sun.spec, (b) => band(T, b), o.r0 ?? 17, o.len ?? 40, o.cA, o.cB, 1.15 * g);
  sun.ring.mesh.scale.setScalar(o.R ?? 68); sun.ring.tint(mixColor(o.cR, WHITE, 0.4 * k), (0.7 + 1.5 * k) * g);
  sun.ring2.mesh.scale.setScalar((o.R ?? 68) * 1.06); sun.ring2.tint(o.cR, 0.6 * g);
  if (o.lead) {
    const R0 = (o.R ?? 68) * 1.22, pc = o.lead;
    updateRibbon(sun.rib, AU.notes.lead, T, 1.85 * BAR, (tau, p, age, out) => { const a = Math.PI / 2 - (tau / (2 * BAR)) * TAU, r = R0 + (p - pc) * 2.0; out[0] = Math.cos(a) * r; out[1] = Math.sin(a) * r; out[2] = 0; }, WHITE, o.cR, 3.2 * g, 2.2);
    sun.rib.mesh.visible = true;
  } else sun.rib.mesh.visible = false;
  sun.flare.position.copy(sun.g.position);
  setFlare(sun.flare, o.flareC ?? GOLD, o.flare ?? 1, T * 0.07, o.flareS ?? 60);
}
// the sky of the other universe (seen through the portal of groove 2, then the place of the heart)
function heartSky(sky, T, dir) {
  const tt = T - 40 * BAR, p = clamp(tt / (16 * BAR)), hk = tt > 0 ? melody(AU.notes.hook, T)[1] : 0;
  sky.turn(T);
  sky.colors(color(0x070209), mixColor(color(0x3a0f2c), color(0x4a1c14), p), mixColor(color(0xd0607a), color(0xe8905a), p), 0.30 + 0.12 * p);
  sky.light(1, dir, mixColor(ROSE, GOLD, 0.2 + 0.6 * p), 0.05 + 0.04 * hk + 0.05 * p, 7);
  sky.light(2, V3b.set(-0.5, 0.6, 0.3), VIO, 0.05, 3);
}
const COLD = new THREE.Color(0.97, 1.0, 1.06), WARM = new THREE.Color(1.05, 0.995, 0.93), HOT = new THREE.Color(1.07, 1.0, 0.9);

// ---- groove 2 (bars 32-40): out of the tunnel; a great portal ahead shows the other universe, and we fly into it ----
MODES.groove2 = {
  build() {
    O.sky = new SkyDome(12);
    O.skyB = new SkyDome(21); O.skyB.mesh.visible = false;
    O.stars = makeStarField(800, [22, 240], 520, 17, {tints: [WHITE, ICE, CYAN, VIO]});
    O.field = makeCrystalField(40, [13, 58], 420, 6, [CYAN, VIO, BLUE, ICE], {gain: 1.4, s0: 0.7, s1: 2.2, kinds: 5});
    O.portal = makePortal(62, O.skyB);
    O.side = [[-25, 9, 0.36], [27, -12, 0.62], [-17, -15, 0.84]].map((q) => { const g = makePortal(7, O.skyB); g.userData.q = q; return g; });
    O.flareB = makeFlare(1, {streak: 1.0, rays: 0.3, inPortal: true});
    O.glints = new Glow(60, {px: 1.6, halo: 1.6, haloGain: 0.5});
  },
  frame(T, t) {
    const L = 8 * BAR, p = clamp(t / L), k = kick(T), clap = hitEnvelope(AU.hits.clap, T, 0.14), lv = level(T), TOT = 560;
    const distAt = (u) => 24 * u * L + (TOT - 24 * L) * Math.pow(u, 1.5), dist = distAt(p), D = TOT - dist + 3;
    const roll = mix(T * 0.06 + 0.1 * Math.sin(T * 0.23), TAU, smootherstep(p)), calm = 1 - smootherstep(p);
    aimCamera(Math.cos(T * 0.5) * 1.5 * calm, Math.sin(T * 0.37) * 1.3 * calm, 0, 0, 0, -80, roll, 64 - 4 * smootherstep(p));
    O.sky.turn(T, 2);
    O.sky.colors(color(0x02010c), color(0x150a48), color(0x2a7fd0), 0.34 + 0.12 * lv);
    O.sky.light(1, V3.set(0, 0, -1), mixColor(CYAN, MAG, clap * 0.6), 0.07 + 0.1 * clap, 8);
    O.sky.light(2, V3.set(0.7, 0.4, -0.5), VIO, 0.04, 3);
    heartSky(O.skyB, T, V3.set(0, 0, -1));
    updateStarField(O.stars, T, dist * 1.2, 1.2 + 2.5 * p, 0, 1);
    updateCrystalField(O.field, T, dist * 2.2, kick(T), (b) => band(T, b), 0, 0.9, 12);
    const eighth = count(T, BEAT / 2), ee = Math.exp(-(T - eighth * BEAT / 2) / 0.12);
    O.portal.position.set(0, 0, -D);
    lightPortal(O.portal, mixColor(ROSE, GOLD, 0.45), 1.8 * (1 + 1.3 * k), WHITE, 0.7, 1 + 0.35 * clap);
    lightDial(O.portal, mixColor(GOLD, WHITE, 0.3), 0.5, eighth, ee);
    O.side.forEach((g, i) => {
      const q = g.userData.q, z = -(distAt(q[2]) - dist);
      g.visible = z < -1.5; g.position.set(q[0], q[1], z); g.rotation.set(0.3 * Math.sin(T * 0.3 + i), -q[0] * 0.02 + 0.3 * Math.sin(T * 0.21 + i * 2), T * 0.1);
      const far = smoothstep(-420, -220, z);
      lightPortal(g, mixColor(ROSE, GOLD, 0.3 + 0.3 * i), 1.6 * far * (1 + 1.3 * k), WHITE, 0.6 * far, far * (1 + 0.35 * clap)); lightDial(g, GOLD, 0.4 * far, eighth, ee * far);
    });
    O.flareB.position.set(0, 0, -D - 95);
    setFlare(O.flareB, mixColor(ROSE, GOLD, 0.5), 0.5, T * 0.04, 30);
    updateGlints(O.glints, AU.notes.call, T, {life: 3.5, c: GOLD, size: 1.6, gain: 4, rise: 0.04, place: (j, pitch) => { const a = hash(j, 1) * TAU, z = -Math.max(D, 70), rr = (70 + 12 * hash(j, 2)) * Math.min(1, -z / 300 + 0.25); return [Math.cos(a) * rr, Math.sin(a) * rr * 0.7 + (pitch - 50) * 0.5, z]; }});      // the choir's groove phrase, two octaves under v6
    const end = smoothstep(7.4 * BAR, 8 * BAR, t);
    finish(T, {exp: 1.02, bloom: 0.7, flash: 1.0 * Math.exp(-t / 0.3) + 0.5 * Math.pow(end, 4), flashCol: mixColor(ICE, GOLD, end), lift: color(0x02020a), gain: mixColor(COLD, WARM, smootherstep(p)), ca: 0.9});
  },
};

// ---- heart (bars 40-56): the other universe. The hook, sung slowly, is a line of light about a great crystal;
//      then the ostinato returns, great rings wake around it and the camera pulls far back ----
MODES.heart = {
  build() {
    O.sky = new SkyDome(21);
    O.shell = makeStarShell(800, 140, 1100, 41, {tints: [WHITE, WHITE, ICE, GOLD, ROSE]});
    O.rings = makeRingStructure();
    O.core = makeCrystal("ico", GOLD, ROSE, {world: 0.2, gain: 1.0, base: 0.045, rim: 0.6}); O.core.scale.setScalar(14);
    O.tes = makeTesseract({world: 0.1}); O.tes.scale.setScalar(3.4);
    O.flare = makeFlare(1, {streak: 1.0, rays: 0.3});
    O.rib = makeRibbon(260, {world: 0.35, px: 1.9});
    O.swarm = makeCrystalSwarm(34, [24, 115], 9, [ROSE, AMBER, GOLD, VIO], {s0: 0.5, s1: 1.7});
    O.shocks = makeShockRings(3, 128);
    O.glints = new Glow(60, {px: 1.6, halo: 1.6, haloGain: 0.5});
    O.glints2 = new Glow(80, {px: 1.6, halo: 1.6, haloGain: 0.5});
    const marks = []; for (let i = 0; i < 16; i++) { const a = (i / 16) * TAU; marks.push(Math.sin(a) * 19, Math.cos(a) * 19, 0, Math.sin(a) * (i % 4 ? 20.2 : 21.6), Math.cos(a) * (i % 4 ? 20.2 : 21.6), 0); }
    O.dial = Glow.from(marks, {px: 1.3, world: 0.14});
  },
  frame(T, t) {
    const tt = T - 40 * BAR, H8 = 8 * BAR, p = clamp(tt / (2 * H8)), u = clamp((tt - H8) / H8), us = u * u * (3 - 2 * u);
    const hk = melody(AU.notes.hook, T)[1], boom = hitEnvelope(AU.hits.boom, T, 1.3), taiko = hitEnvelope(AU.hits.taiko, T, 0.5), frame = hitEnvelope(AU.hits.frame, T, 0.22);
    const r = tt < H8 ? mix(95, 50, smootherstep(tt / H8)) : 50 + 420 * us, th = 0.05 * tt + 0.5 * us, y = 3 + r * 0.1 + 110 * us;
    const off = r * 0.16 * smoothstep(0, 2.5 * BAR, tt) * (1 - us);
    aimCamera(Math.sin(th) * r, y, Math.cos(th) * r, Math.cos(th) * off, 1 - 4 * us, -Math.sin(th) * off, 0.04 * Math.sin(T * 0.11), 52 + 4 * us);
    heartSky(O.sky, T, V3.copy(C.position).negate());
    if (taiko > 0.01) { const ti = lastIndex(AU.hits.taiko.t, T); O.sky.light(2, V3b.set(Math.cos(ti * 2.4), 0.3 + 0.4 * Math.sin(ti * 1.7), Math.sin(ti * 2.4)), mixColor(AMBER, WHITE, 0.3), 0.3 * taiko, 4); }
    O.shell.tint(WHITE, 1);
    const ost = ostEnv(T, 0.1);
    updateRingStructure(O.rings, T, (q) => mixColor(ROSE, AMBER, 0.2 + 0.12 * q + 0.25 * u), (q) => smoothstep(q * 0.1 - 0.12, q * 0.1 + 0.25, (tt - 7 * BAR) / (9 * BAR)) * (0.4 + 0.25 * u) * (1 + 0.9 * u * ostEnv(T - q * 0.03, 0.12)) * (1 + 0.8 * taiko));
    O.core.rotation.set(T * 0.05, T * 0.08, 0); lightCrystal(O.core, clamp(0.3 * hk + 0.5 * boom), 1);
    updateTesseract(O.tes, tesseractAngles(T * 0.3 + 1), mixColor(GOLD, WHITE, 0.3 + 0.5 * hk), 1.2 + 1.4 * hk + boom, 2.4 + 4 * frame + 1.5 * ost * u);
    O.flare.position.set(0, 0, 0);
    setFlare(O.flare, mixColor(ROSE, GOLD, 0.5 + 0.5 * p), 0.3 + 0.4 * hk + 0.7 * boom + 0.4 * taiko, T * 0.04, (22 + 6 * hk) * (1 + 1.6 * us));
    const wide = 1 + 2.2 * us;
    updateRibbon(O.rib, AU.notes.hook, T, 9, (tau, pitch, age, out) => { const a = tau * 0.85, rr = (21 + age * 2.4) * wide; out[0] = Math.cos(a) * rr; out[1] = (pitch - 62) * 1.3 * wide; out[2] = Math.sin(a) * rr; }, mixColor(GOLD, WHITE, 0.5), ROSE, 3.2, 3.5);
    O.rib.mat.uniforms.uWorld.value = 0.35 * wide;
    updateCrystalSwarm(O.swarm, T, 0.35 * hk + 0.5 * taiko, (b) => band(T, b), 0.9);
    updateShockRings(O.shocks, AU.hits.boom, T, mixColor(ROSE, GOLD, p), {at: ORIGIN, r0: 15, r1: 260, life: 5.5, gain: 2.2, face: true});
    updateGlints(O.glints, AU.notes.swell, T, {life: 4, rise: 0.4, c: ROSE, size: 1.5 * wide, gain: 4, place: (j) => { const a = hash(j, 1) * TAU, rr = (30 + 26 * hash(j, 2)) * wide; return [Math.cos(a) * rr, (hash(j, 3) - 0.5) * 44 * wide, Math.sin(a) * rr]; }});
    updateGlints(O.glints2, AU.notes.call, T, {n: 16, life: 3, rise: 0.07, c: GOLD, size: 2.6 * wide, gain: 4.5, place: (j, pitch) => { const a = j * 0.72; return [Math.cos(a) * 70, (pitch - 64) * 2.4, Math.sin(a) * 70]; }});   // violas, an octave under v6's violins
    tickDial(O.dial, T, GOLD, 0.15);
    finish(T, {exp: 0.95 + 0.05 * p, bloom: 0.7, flash: 0.6 * Math.exp(-tt / 0.5) + 0.2 * hitEnvelope(AU.hits.boom, T, 0.35) * smoothstep(1, 2, tt), flashCol: mixColor(ROSE, GOLD, 0.5), lift: color(0x060204), gain: WARM, vig: 0.7, ca: 0.5});
  },
};

// ---- build (bars 56-64): the corridor again, hot and faster and faster towards a white star; then a breath of dark ----
MODES.build = {
  build() {
    O.sky = new SkyDome(25);
    O.stars = makeStarField(900, [20, 260], 600, 19, {tints: [WHITE, GOLD, AMBER, ROSE]});
    O.lat = makeLattice(14, 22, 12);
    O.field = makeCrystalField(26, [17, 46], 320, 8, [AMBER, GOLD, ROSE, ORANGE], {gain: 1.4, s0: 0.6, s1: 1.4, kinds: 5});
    O.flare = makeFlare(1, {streak: 1.6, rays: 0.7});
    O.tes = makeTesseract({world: 0.4}); O.tes.scale.setScalar(9);
  },
  frame(T, t) {
    const tt = T - 56 * BAR, L = 8 * BAR, p = clamp(tt / L), k = kick(T), taiko = hitEnvelope(AU.hits.taiko, T, 0.3), tom = hitEnvelope(AU.hits.tom, T, 0.2), roll = hitEnvelope(AU.hits.roll, T, 0.09);
    const gap = smoothstep(7.6 * BAR, 7.68 * BAR, tt), live = 1 - gap, dist = 40 * tt + 70 * tt * tt / L, hot = p * p;
    aimCamera(1.4 * Math.sin(T * 0.4) * live, 1.2 * Math.cos(T * 0.31) * live, 0, 0, 0, -100, 0.02 * tt * tt, 58 + 12 * hot);
    O.sky.turn(T, 2);
    O.sky.colors(color(0x080203), mixColor(color(0x3a1008), color(0x6a2a08), p), mixColor(color(0xff7a30), color(0xffd9a0), hot), (0.36 + 0.5 * hot) * (0.04 + 0.96 * live));
    O.sky.light(1, V3.set(0, 0, -1), mixColor(AMBER, WHITE, hot), (0.1 + 0.5 * hot + 0.12 * roll * p) * live, 7 - 3 * hot);
    const ti = lastIndex(AU.hits.tom.t, T);
    O.sky.light(2, V3.set(Math.cos(ti * 2.4) * 0.8, Math.sin(ti * 1.7) * 0.6, -0.6), mixColor(ORANGE, GOLD, 0.5), 0.3 * tom * live, 5);
    updateStarField(O.stars, T, dist * 0.6, 1 + 9 * hot, 0, live);
    updateLattice(O.lat, T, dist, 0, mixColor(ORANGE, WHITE, 0.15 + 0.6 * hot), (i, ahead) => live * (0.2 + 0.25 * p + 1.6 * ostEnv(tt - ahead / 500) + (1.2 + p) * k * Math.exp(-ahead / 140) + 1.5 * taiko * Math.exp(-ahead / 80) + 0.8 * roll * p), 0.5);
    updateCrystalField(O.field, T, dist, kick(T), (b) => band(T, b), 0, live, 12);
    O.flare.position.set(0, 0, -420); O.tes.position.set(0, 0, -420);
    updateTesseract(O.tes, tesseractAngles(T * 0.6), mixColor(GOLD, WHITE, hot), (1.4 + 1.5 * k) * live, (3 + 3 * k) * live);
    setFlare(O.flare, mixColor(AMBER, WHITE, 0.3 + 0.7 * hot), (0.6 + 1.8 * hot + 0.4 * k) * live + 0.6 * gap, T * 0.12, (50 + 170 * hot) * live + 44 * gap);
    finish(T, {exp: 1.0 + 0.45 * hot * live, bloom: 0.7 + 0.25 * hot, flash: 0.7 * Math.exp(-tt / 0.3) + 0.9 * Math.pow(p, 7) * live, flashCol: mixColor(AMBER, WHITE, 0.6), lift: color(0x050203), gain: mixColor(WARM, HOT, p), vig: 0.6, ca: 0.6 + 1.2 * hot});
  },
};

// ---- drop 1 (bars 64-72): the sun. The spectrum is its rays, the lead is its orbit, the kick sends rings down the flight ----
function dropSky(sky, T, hotter = 0) {
  const lv = level(T), clap = hitEnvelope(AU.hits.clap, T, 0.16);
  sky.colors(color(0x09020e), mixColor(color(0x4a0a3a), color(0x5a1a0c), hotter), mixColor(color(0xff6a3a), color(0xffc070), hotter), 0.27 + 0.13 * lv + 0.08 * hotter);
  return clap;
}
MODES.drop1 = {
  build() {
    O.sky = new SkyDome(30);
    O.stars = makeStarField(900, [24, 280], 620, 23, {tints: [WHITE, GOLD, ROSE, MAG]});
    O.tun = new Glow(14 * 8, {px: 1.5, world: 0.1, halo: 1.6, haloGain: 0.35, max: 5});
    O.field = makeCrystalField(34, [19, 62], 300, 14, [MAG, ORANGE, GOLD, VIO], {gain: 1.5, s0: 0.7, s1: 1.8, kinds: 5});
    O.sun = makeSun();
    O.shocks = makeShockRings(3, 128);
  },
  frame(T, t) {
    const v = 92, k = kick(T), snare = hitEnvelope(AU.hits.snare, T, 0.2), taiko = hitEnvelope(AU.hits.taiko, T, 0.4), DS = 265;
    const roll = 0.22 * Math.sin(T * 0.21) + 0.05 * t;
    aimCamera(Math.cos(T * 0.5) * 2.6, Math.sin(T * 0.37) * 2.2, 0, Math.cos(T * 0.31) * 14, Math.sin(T * 0.26) * 9, -DS, roll, 64);
    O.sky.turn(T, 2.5);
    const clap = dropSky(O.sky, T, 0);
    O.sky.light(1, V3.set(0, 0, -1), mixColor(ORANGE, GOLD, 0.4), 0.09 + 0.14 * taiko, 5);
    O.sky.light(2, V3.set(Math.cos(T * 0.2) * 0.8, 0.5, -0.4), MAG, 0.05 + 0.14 * clap, 4);
    updateStarField(O.stars, T, v * T * 0.7, 3.2, 0, 1);
    updateTunnel(O.tun, T, BEAT, (tk) => -(tk - T) * v - 3, 520, 15, (idx, tk) => { const bar = count(tk, BAR); return [mixColor(bar % 2 ? MAG : ORANGE, WHITE, 0.55 * k), 1.1 + 2.8 * k, POLY[bar % 4]]; });
    updateCrystalField(O.field, T, v * T * 0.8, kick(T), (b) => band(T, b), 0, 0.95, 12);
    O.sun.g.position.set(0, 0, -DS); O.sun.g.quaternion.copy(C.quaternion);
    updateSun(O.sun, T, {k, cA: mixColor(GOLD, ORANGE, 0.45), cB: MAG, cR: mixColor(ORANGE, GOLD, 0.5), r0: 17, len: 42, R: 70, lead: 85, flare: 0.24 + 0.26 * k + 0.2 * taiko, flareC: mixColor(ORANGE, GOLD, 0.6), flareS: 46});
    updateShockRings(O.shocks, AU.hits.taiko, T, mixColor(GOLD, WHITE, 0.4), {at: O.sun.g.position, r0: 20, r1: 300, life: 2.6, gain: 3, face: true, only: (tj) => Math.abs(tj / (4 * BAR) - Math.round(tj / (4 * BAR))) < 0.01});
    finish(T, {exp: 1.0, bloom: 0.7, flash: 1.3 * Math.exp(-t / 0.28), flashCol: mixColor(GOLD, WHITE, 0.6), lift: color(0x060208), gain: WARM, sat: 1.12, ca: 1.0, vig: 0.5});
  },
};

// ---- drop 2 (bars 72-80): around the sun; five portals show the cold universe we came from ----
MODES.drop2 = {
  build() {
    O.sky = new SkyDome(30);
    O.skyB = new SkyDome(3); O.skyB.mesh.visible = false;
    O.shell = makeStarShell(700, 180, 1000, 43, {tints: [WHITE, GOLD, ROSE, MAG]});
    O.shellB = makeStarShell(500, 200, 900, 47, {tints: [WHITE, ICE, CYAN], inPortal: true});
    O.sun = makeSun();
    O.portals = [0, 1, 2, 3, 4].map((i) => {
      const g = makePortal(26, O.skyB), a = (i / 5) * TAU; g.userData.a = a;
      const tes = makeTesseract({world: 0.3, inPortal: true}); tes.position.set(Math.sin(a) * 215, 0, Math.cos(a) * 215); tes.scale.setScalar(13); g.userData.tes = tes;
      return g;
    });
    O.swarm = makeCrystalSwarm(40, [84, 190], 15, [MAG, ORANGE, GOLD, VIO], {s0: 1.0, s1: 3.2, world: 0.1});
    O.shocks = makeShockRings(3, 128);
  },
  frame(T, t) {
    const k = kick(T), taiko = hitEnvelope(AU.hits.taiko, T, 0.4), p = clamp(t / (8 * BAR));
    const th = 0.4 + t * 0.2, r = 245 - 30 * Math.sin(t * 0.33), y = 60 * Math.sin(t * 0.24 + 0.6);
    aimCamera(Math.sin(th) * r, y, Math.cos(th) * r, 0, 0, 0, 0.14 * Math.sin(T * 0.19), 62);
    O.sky.turn(T, 2.5); O.skyB.turn(T);
    const clap = dropSky(O.sky, T, 0.3 * p);
    O.sky.light(1, V3.copy(C.position).negate(), mixColor(ORANGE, GOLD, 0.5), 0.09 + 0.14 * taiko, 5);
    O.sky.light(2, V3b.set(Math.cos(T * 0.2) * 0.8, 0.5, Math.sin(T * 0.2)), MAG, 0.05 + 0.14 * clap, 4);
    O.skyB.colors(color(0x00030a), color(0x04264a), color(0x28b4dc), 0.5);
    O.skyB.light(1, V3.copy(C.position).negate(), CYAN, 0.05, 6); O.skyB.light(2, V3b.set(0, 1, 0), BLUE, 0.05, 3);
    O.shell.tint(WHITE, 1); O.shellB.tint(WHITE, 1.3);
    O.sun.g.rotation.set(0, th * 0.75, T * 0.03);
    updateSun(O.sun, T, {k, cA: mixColor(GOLD, ORANGE, 0.45), cB: MAG, cR: mixColor(ORANGE, GOLD, 0.6), r0: 17, len: 44, R: 60, lead: 85, flare: 0.2 + 0.22 * k + 0.2 * taiko, flareC: mixColor(ORANGE, GOLD, 0.6), flareS: 44, gain: 0.85});
    const eighth = count(T, BEAT / 2), ee = Math.exp(-(T - eighth * BEAT / 2) / 0.12);
    O.portals.forEach((g, i) => {
      const a = g.userData.a + T * 0.05, R = 108, on = count(T, BEAT) % 5 === i ? k : 0.25 * k;
      g.position.set(Math.sin(a) * R, 26 * Math.sin(T * 0.13 + i * 1.9), Math.cos(a) * R); g.rotation.set(0, a, 0);
      lightPortal(g, mixColor(CYAN, WHITE, 0.5 * on), 0.9 + 1.8 * on, ICE, 0.5, 1 + 0.3 * clap); lightDial(g, ICE, 0.45, eighth + i * 9, ee);
      const tes = g.userData.tes; tes.position.set(Math.sin(a) * 235, g.position.y, Math.cos(a) * 235);
      updateTesseract(tes, tesseractAngles(T * 0.5 + i), mixColor(CYAN, ICE, 0.5), 1.6 + 1.6 * on, 3);
    });
    updateCrystalSwarm(O.swarm, T, k, (b) => band(T, b), 0.95);
    updateShockRings(O.shocks, AU.hits.taiko, T, mixColor(GOLD, WHITE, 0.4), {at: ORIGIN, r0: 20, r1: 330, life: 2.6, gain: 3, face: true, only: (tj) => Math.abs(tj / (4 * BAR) - Math.round(tj / (4 * BAR))) < 0.01});
    finish(T, {exp: 1.0, bloom: 0.7, flash: 1.0 * Math.exp(-t / 0.28), flashCol: mixColor(MAG, WHITE, 0.6), lift: color(0x060208), gain: WARM, sat: 1.12, ca: 0.9, vig: 0.5});
  },
};

// ---- climax (bars 80-88) and afterglow (bars 88-96): the sun inside the great rings, and all of it seen from far away ----
function megaBuild(seed) {
  O.sky = new SkyDome(seed);
  O.shell = makeStarShell(900, 320, 1500, 51, {tints: [WHITE, WHITE, GOLD, ROSE]});
  O.rings = makeRingStructure();
  O.sun = makeSun();
  O.swarm = makeCrystalSwarm(44, [44, 270], 21, [GOLD, MAG, AMBER, ROSE], {s0: 1.2, s1: 4.5, world: 0.14, tilt: 0.5});
  O.shocks = makeShockRings(3, 160);
  O.glints = new Glow(80, {px: 1.8, halo: 1.6, haloGain: 0.5});
  O.rib = makeRibbon(220, {world: 0.9, px: 2.0, max: 8});
}
const megaCam = (tc) => { const p = clamp(tc / (8 * BAR)), q = clamp(tc / (8 * BAR) - 1), r = 150 + 520 * p * p * (3 - 2 * p) - 400 * q * q * (3 - 2 * q); return {r, th: 0.9 + 0.11 * Math.min(tc, 8 * BAR) + 0.05 * Math.max(0, tc - 8 * BAR), y: 14 + r * 0.3}; };
MODES.climax = {
  build() { megaBuild(33); },
  frame(T, t) {
    const tc = T - 80 * BAR, p = clamp(tc / (8 * BAR)), k = kick(T), taiko = hitEnvelope(AU.hits.taiko, T, 0.4), crash = hitEnvelope(AU.hits.crash, T, 0.5), cam = megaCam(tc);
    aimCamera(Math.sin(cam.th) * cam.r, cam.y, Math.cos(cam.th) * cam.r, 0, -cam.r * 0.04, 0, 0.1 * Math.sin(T * 0.17), 58);
    O.sky.turn(T, 2);
    const clap = hitEnvelope(AU.hits.clap, T, 0.16);
    O.sky.colors(color(0x0b0410), color(0x5e0e26), color(0xffb060), 0.27 + 0.12 * level(T) + 0.05 * p);
    O.sky.light(1, V3.copy(C.position).negate(), mixColor(GOLD, WHITE, 0.5), 0.13 + 0.14 * taiko + 0.08 * crash, 4.5);
    O.sky.light(2, V3b.set(Math.cos(T * 0.2), 0.6, Math.sin(T * 0.2)), ROSE, 0.05 + 0.12 * clap, 4);
    O.shell.tint(WHITE, 1.1);
    updateRingStructure(O.rings, T, (q) => mixColor(q % 2 ? GOLD : WHITE, AMBER, 0.25), (q) => (0.5 + 0.1 * q) * (1 + 1.5 * (count(T, BEAT) % 5 === q ? k : 0.45 * k)) * (1 + 0.5 * taiko), 2.2);
    O.sun.g.rotation.set(-1.15, 0, T * 0.06);
    updateSun(O.sun, T, {k, cA: WHITE, cB: ORANGE, cR: GOLD, r0: 17, len: 52, R: 82, lead: 90, flare: 0.5 + 0.4 * k + 0.35 * taiko, flareC: mixColor(GOLD, WHITE, 0.4), flareS: 50 + cam.r * 0.1, gain: 1.1});
    updateCrystalSwarm(O.swarm, T, k, (b) => band(T, b), 1);
    updateShockRings(O.shocks, AU.hits.taiko, T, mixColor(GOLD, WHITE, 0.5), {at: ORIGIN, r0: 20, r1: 520, life: 3.2, gain: 3.2, face: true, only: (tj) => Math.abs(tj / (2 * BAR) - Math.round(tj / (2 * BAR))) < 0.01});
    updateGlints(O.glints, AU.notes.call, T, {n: 16, life: 2.2, rise: 0.04, c: GOLD, size: 5 + cam.r * 0.012, gain: 5, place: (j, pitch) => { const a = j * 0.55; return [Math.cos(a) * 118, (pitch - 56) * 3.4 + 20, Math.sin(a) * 118]; }});   // violas, an octave under v6
    O.rib.mesh.visible = false;
    finish(T, {exp: 1.03, bloom: 0.75, flash: 1.5 * Math.exp(-tc / 0.3) + 0.3 * crash * smoothstep(1, 2, tc), flashCol: mixColor(GOLD, WHITE, 0.7), lift: color(0x070402), gain: HOT, sat: 1.1, ca: 0.9, vig: 0.5});
  },
};
MODES.afterglow = {
  build() { megaBuild(33); },
  frame(T, t) {
    const tc = T - 80 * BAR, ta = T - 88 * BAR, p = clamp(ta / (8 * BAR)), k = kick(T) * (1 - 0.75 * p), taiko = hitEnvelope(AU.hits.taiko, T, 0.6), boom = hitEnvelope(AU.hits.boom, T, 1.2), cam = megaCam(tc), hk = melody(AU.notes.hook, T)[1];
    aimCamera(Math.sin(cam.th) * cam.r, cam.y, Math.cos(cam.th) * cam.r, 0, -cam.r * 0.04, 0, 0.1 * Math.sin(T * 0.17), 58 - 4 * p);
    O.sky.turn(T, 2 - p);
    O.sky.colors(color(0x070308), mixColor(color(0x5e0e26), color(0x1c1040), p), mixColor(color(0xffb060), color(0x8a66d8), p), 0.32 - 0.06 * p);
    O.sky.light(1, V3.copy(C.position).negate(), mixColor(GOLD, ROSE, p), 0.12 - 0.05 * p + 0.12 * taiko + 0.04 * hk, 5);
    O.sky.light(2, V3b.set(Math.cos(T * 0.2), 0.6, Math.sin(T * 0.2)), VIO, 0.06, 4);
    O.shell.tint(WHITE, 1.1);
    updateRingStructure(O.rings, T, (q) => mixColor(mixColor(GOLD, AMBER, 0.25), q % 2 ? VIO : ROSE, p), (q) => (0.62 - 0.3 * p) * (1 + 1.2 * k) * (1 + 0.5 * taiko), 2.2 - 1.2 * p);
    O.sun.g.rotation.set(-1.15, 0, T * 0.06);
    updateSun(O.sun, T, {k, cA: mixColor(WHITE, ROSE, p), cB: mixColor(ORANGE, VIO, p), cR: mixColor(GOLD, ROSE, p), r0: 17, len: 52 - 20 * p, R: 82, flare: 0.45 - 0.1 * p + 0.35 * k + 0.3 * taiko + 0.25 * hk, flareC: mixColor(GOLD, ROSE, 0.6 * p), flareS: 50 + cam.r * 0.1, gain: 1.1 - 0.4 * p});
    updateCrystalSwarm(O.swarm, T, clamp(k + 0.3 * hk), (b) => band(T, b), 1 - 0.3 * p);
    updateShockRings(O.shocks, AU.hits.taiko, T, mixColor(GOLD, ROSE, p), {at: ORIGIN, r0: 20, r1: 520, life: 5, gain: 2.6, face: true});
    updateRibbon(O.rib, AU.notes.hook, T, 9, (tau, pitch, age, out) => { const a = tau * 0.6, rr = 96 + age * 7; out[0] = Math.cos(a) * rr; out[1] = (pitch - 62) * 4.2 + 22; out[2] = Math.sin(a) * rr; }, mixColor(GOLD, WHITE, 0.5), ROSE, 3.4, 3.5);
    O.rib.mesh.visible = true;
    updateGlints(O.glints, AU.notes.swell, T, {n: 16, life: 4, rise: 0.4, c: ROSE, size: 4, gain: 4, place: (j) => { const a = hash(j, 1) * TAU, rr = 110 + 60 * hash(j, 2); return [Math.cos(a) * rr, (hash(j, 3) - 0.3) * 90, Math.sin(a) * rr]; }});
    finish(T, {exp: 1.03 - 0.03 * p, bloom: 0.75, flash: 0.5 * Math.exp(-ta / 0.6), flashCol: mixColor(GOLD, WHITE, 0.5), lift: mixColor(color(0x070402), color(0x040308), p), gain: mixColor(HOT, ONE, p), sat: 1.1 - 0.06 * p, ca: 0.7, vig: 0.55 + 0.1 * p});
  },
};

// ---- coda (bars 96-104 and the last chord's tail): the one light again, far in a large dark, now warm, in the left
//      third; the end card in the right third (the opening mirrored) ----
const TAIL = 4.6;
MODES.coda = {
  build() {
    O.sky = new SkyDome(3);
    O.stars = makeStarField(900, [14, 260], 620, 11);
    O.dust = makeStarField(160, [3, 40], 160, 29, {px: 3.2, tints: [ICE, GOLD, WHITE]});
    O.tes = makeTesseract({world: 0.05}); O.tes.position.set(0, 0, -150); O.tes.scale.setScalar(6.5);
    O.flare = makeFlare(1, {streak: 1.0, rays: 0.3}); O.flare.position.copy(O.tes.position);
    O.shocks = makeShockRings(3);
    O.glints = new Glow(80, {px: 1.6, halo: 1.6, haloGain: 0.5});
    const marks = []; for (let i = 0; i < 16; i++) { const a = (i / 16) * TAU; marks.push(Math.sin(a) * 15, Math.cos(a) * 15, 0, Math.sin(a) * (i % 4 ? 16.2 : 17.4), Math.cos(a) * (i % 4 ? 16.2 : 17.4), 0); }
    O.dial = Glow.from(marks, {px: 1.3, world: 0.12}); O.dial.mesh.position.copy(O.tes.position);
  },
  frame(T, t) {
    const L = 8 * BAR, END = L + TAIL, p = clamp(t / L), boom = hitEnvelope(AU.hits.boom, T, 1.4), taiko = hitEnvelope(AU.hits.taiko, T, 0.8), hk = noteLevel(AU.notes.hook, T, 0.3, 2.5);
    const major = smoothstep(3.6 * BAR, 6.5 * BAR, t), out = 1 - smoothstep(END - 2.6, END - 0.4, t), shown = card.update(t);
    card.element.style.opacity = (shown * out).toFixed(3);                                                                  // the card fades with the picture
    const cz = -62 + 70 * smootherstep(t / END), cx = Math.sin(T * 0.11) * 2.4;
    const aside = SIDE * (150 + cz) * smootherstep(clamp(t / (4.3 * BAR)));                                                 // the light moves into the left third
    aimCamera(cx, 1.0 + Math.cos(T * 0.09) * 1.2, cz, cx + aside, 0, -150, 0.03 * Math.sin(T * 0.13), 50);
    O.sky.turn(T);
    O.sky.colors(color(0x010207), mixColor(color(0x051a33), color(0x1a1430), major), mixColor(color(0x3a80a0), color(0xd08a5a), major), 0.5 - 0.2 * shown);
    O.sky.light(1, V3.set(0, -0.3, -1), mixColor(ICE, GOLD, 0.3 + 0.7 * major), 0.06 + 0.16 * major + 0.1 * boom + 0.05 * hk, 9);
    O.sky.light(2, V3.set(-0.6, 0.5, -0.4), BLUE, 0.035, 3);
    updateStarField(O.stars, T, -4 * t, 0.0, cz, 1);
    updateStarField(O.dust, T, -2 * t, 0.0, cz, 0.12, 4);
    const warm = mixColor(ICE, GOLD, 0.25 + 0.75 * major);
    updateTesseract(O.tes, tesseractAngles(T * 0.35 + 2), mixColor(warm, WHITE, boom), 1.2 + 2.0 * boom + 0.6 * hk + 0.5 * major, 2.4 + 3 * boom);
    setFlare(O.flare, warm, 0.7 + 1.4 * boom + 0.5 * hk + 0.6 * major + 0.5 * taiko, T * 0.05, 28 + 10 * boom + 14 * major);
    updateShockRings(O.shocks, AU.hits.boom, T, warm, {at: O.tes.position, r0: 6, r1: 170, life: 6, gain: 2.2 * (1 - 0.6 * shown), face: true});
    tickDial(O.dial, T, warm);
    const bt = AU.notes.call.t;
    updateGlints(O.glints, AU.notes.call, T, {n: 16, life: 4.5, rise: 0.08, c: GOLD, size: 2.0, gain: 5, place: (j) => { const s = (bt[j] / S16) % 32, side = j % 2 ? 1 : -1; return [-45 + side * (12 + 1.8 * s), -52 + 3.4 * s + 10 * hash(j, 2), -150 + 30 * (hash(j, 3) - 0.5)]; }});   // around the light, off the card
    finish(T, {exp: 1.0 - 0.12 * shown, bloom: 0.7, fade: out, flash: 0.6 * Math.exp(-t / 0.6), flashCol: mixColor(ROSE, WHITE, 0.5), lift: mixColor(color(0x020409), color(0x050304), major), gain: mixColor(COLD, WARM, major), vig: 0.7});
  },
};

// ====================================================================================================
// the opening title and the end card (vidgen/title-cards: Escapement's type, timing and layout). The title comes up
// over bars 2-3, settles, holds and is gone by bar 7.5, before the first cut; the end card mirrors it on the right
// from bar 3 of the coda and fades out with the picture. The project's link is on the end card only.
const TITLE = "PARALLEL SPACE", LINK = "https://github.com/joaopauloschuler/schu-video-generator";
async function makeCard(ctx) {
  if (mode === "dawn") return titleCard(ctx, {title: TITLE, subtitle: "A flight through parallel realities", shade: 0.7, start: BAR, fadeIn: 2 * BAR, hold: 3 * BAR, fadeOut: 1.5 * BAR});
  if (mode === "coda") return endCard(ctx, {title: TITLE, subtitle: "Made with schu-video-generator", link: LINK, shade: 0.7, start: 3 * BAR});
  return null;
}

export async function load(ctx) {
  mode = ctx.data.mode; M = ctx.music; t0 = M.t0; W = ctx.width; H = ctx.height;
  AU = trackArrays(M, {hits: HIT_TRACKS, notes: NOTE_TRACKS, grid: S16});
  document.documentElement.style.background = "#000"; document.body.style.background = "#000"; document.body.style.margin = "0"; document.body.style.overflow = "hidden";
  R = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false, stencil: true, powerPreference: "high-performance"});
  R.setPixelRatio(1); R.setSize(W, H, false); R.setClearColor(0x000000, 1); R.toneMapping = THREE.NoToneMapping;
  uRes.value.set(W, H);
  S = new THREE.Scene();
  C = new THREE.PerspectiveCamera(55, W / H, 0.3, 4000);
  setStage({renderer: R, scene: S, camera: C, width: W, height: H});
  card = await makeCard(ctx);
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
