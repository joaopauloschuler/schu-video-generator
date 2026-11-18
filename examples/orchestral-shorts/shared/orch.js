// Orchestral shorts: one three.js module for every shot of a portrait music video (data.mode picks the set).
// Built on vidgen/three-kit, vidgen/music-time, vidgen/three-finish, vidgen/title-cards.
//
// Everything is drawn from the song time T = ctx.music.time(t): nothing is carried between frames, so shots cut on
// bar lines and render in any order. Rules kept from the owner's notes:
//  - hits light SELECTED objects (a crystal, a portal's ring, a tesseract, the swarm, the tunnel's rings, a flare):
//    never the sky, never the whole frame, never the zoom or a size;
//  - every rotation and camera move is a slow, smooth function of time (no beat flicks);
//  - geometry stays at least ~12 units from the camera (nothing sweeps through the near plane as stripes);
//  - abstract cosmic space only (no city, no land).
import * as THREE from "three";
import {reactions, orbit, smootherstep, smoothstep, clamp, hash, count, trackArrays} from "vidgen/music-time";
import {setStage, color, mixColor, WARM_WHITE, Glow, SkyDome, makeStarField, updateStarField, makeStarShell, makeFlare, setFlare,
  makeCrystal, lightCrystal, POLYHEDRA, makePortal, lightPortal, lightDial, makeTesseract, updateTesseract, tesseractAngles,
  makeCrystalSwarm, updateCrystalSwarm, makeShockRings, updateShockRings, updateGlints, makeRibbon, updateRibbon,
  makeSpectrumRays, updateSpectrumRays, updateTunnel, makeRingStructure, updateRingStructure, aimCamera} from "vidgen/three-kit";
import {Finish} from "vidgen/three-finish";
import {titleCard, endCard} from "vidgen/title-cards";

const TAU = Math.PI * 2;
const URL = "https://github.com/joaopauloschuler/schu-video-generator";
let M, D, R, song, finish, camera, scene, sky, card, label, O = {};
let BASE, ACC, DEEP, FOV, DIR, LOOKY;

// ---------- the sets ----------
// each: build() once in load, update(T, u, e) every frame; u: 0..1 over the shot (eased), e: {pulse, glow, band}
const SETS = {
  // a slow flight through a nebula and stars towards a far light; notes leave glints in the distance
  drift: {
    build() {
      O.stars = makeStarField(700, [14, 150], 340, D.seed + 1);
      O.flare = makeFlare(70, {streak: 0.7, rays: 0.35}); O.flare.position.set(0, 10, -190);
    },
    update(T, u, e) {
      aimCamera(0, 0, 0, 18 * Math.sin(T * 0.045 + D.seed), 6 + LOOKY + 3 * Math.sin(T * 0.06), -100, 0.05 * Math.sin(T * 0.11), FOV);
      updateStarField(O.stars, T, 7 * T, 0.4, 0, 0.9 + 0.3 * e.glow, 14);
      setFlare(O.flare, mixColor(BASE, WARM_WHITE, 0.35), 0.7 + 1.1 * e.pulse + 0.3 * e.glow, T * 0.04, 1);
      glints(T, (i, p) => [(hash(i, 1) - 0.5) * 50, (p ? p - 64 : 0) * 0.9 + (hash(i, 7) - 0.5) * 16 + 8, -55 - 45 * hash(i, 3)]);
    },
  },
  // one great glass crystal turning slowly in a shell of stars; the drums light it
  crystal: {
    build() {
      O.shell = makeStarShell(900, 90, 260, D.seed + 2);
      O.crys = makeCrystal(D.kind ?? POLYHEDRA[D.seed % 5], BASE.clone(), ACC.clone(), {gain: 1.7, world: 0.07, rim: 0.6});
      O.crys.scale.setScalar(D.size ?? 4.6);
      O.halo = makeFlare(26, {streak: 0.4, rays: 0.25}); O.halo.position.set(0, 0, 0);
    },
    update(T, u, e) {
      O.crys.rotation.set(0.35 + T * 0.11, T * 0.17 * DIR, 0.2 * Math.sin(T * 0.07));
      lightCrystal(O.crys, Math.min(1.2, e.pulse), 0.9 + 0.3 * e.glow);
      setFlare(O.halo, mixColor(BASE, WARM_WHITE, 0.3), 0.35 + 0.35 * e.glow, T * 0.03, 1);
      const [x, y, z] = orbit(T, {radius: 24 - 3 * u, height: 3, speed: 0.1 * DIR, phase: D.seed, bob: 1.5});
      aimCamera(x, y, z, 0, LOOKY, 0, 0.03 * Math.sin(T * 0.13), FOV);
      glints(T, (i, p) => { const a = hash(i, 2) * TAU, b = (hash(i, 5) - 0.5) * 2.2; return [Math.cos(a) * 9.5 * Math.cos(b), Math.sin(b) * 9.5 + (p ? (p - 64) * 0.08 : 0), Math.sin(a) * 9.5 * Math.cos(b)]; });
    },
  },
  // a ring of light with a window onto another sky; a tesseract floats inside it; the dial runs on the eighths
  portal: {
    build() {
      O.shell = makeStarShell(700, 90, 260, D.seed + 3);
      O.inner = new SkyDome(D.seed + 11); O.inner.mesh.visible = false;
      O.portal = makePortal(10, O.inner);
      O.tes = makeTesseract({inPortal: true, world: 0.06}); O.tes.position.set(0, 0, -34); O.tes.scale.setScalar(5.5);
    },
    update(T, u, e) {
      O.inner.turn(T, 3);
      O.inner.colors(DEEP.clone().multiplyScalar(0.6), mixColor(ACC, DEEP, 0.6, 0.25), ACC.clone().multiplyScalar(0.55), 0.8 + 0.3 * e.glow);
      lightPortal(O.portal, BASE, 1.3 + 1.6 * e.pulse, WARM_WHITE, 0.55, 0.9);
      lightDial(O.portal, ACC, 0.25, count(T, song.beat / 2), 0.9);
      updateTesseract(O.tes, tesseractAngles(T * 0.55), mixColor(ACC, WARM_WHITE, 0.25), 1.4 + 1.2 * e.pulse, 2.2);
      const z = 40 - 12 * u, x = 9 * Math.sin(T * 0.07 + D.seed) * (1 - 0.5 * u);
      aimCamera(x, 2 + 2 * Math.sin(T * 0.05), z, 0, LOOKY * 0.8, 0, 0.04 * Math.sin(T * 0.1), FOV);
    },
  },
  // a hypercube turning in four dimensions, glints around it
  tesseract: {
    build() {
      O.shell = makeStarShell(900, 90, 260, D.seed + 4);
      O.tes = makeTesseract({world: 0.07}); O.tes.scale.setScalar(D.size ?? 3.4);
      O.swarm = makeCrystalSwarm(14, [34, 60], D.seed, [BASE, ACC, WARM_WHITE], {gain: 0.9});
    },
    update(T, u, e) {
      updateTesseract(O.tes, tesseractAngles(T * 0.6, 0.3 * D.seed), mixColor(BASE, WARM_WHITE, 0.15), 1.5 + 1.8 * e.pulse, 2.4 + 2 * e.pulse);
      updateCrystalSwarm(O.swarm, T, 0, e.band, 0.6 + 0.3 * e.glow);
      const [x, y, z] = orbit(T, {radius: 27 - 3 * u, height: 4, speed: 0.12 * DIR, phase: D.seed * 0.7, bob: 2});
      aimCamera(x, y, z, 0, LOOKY, 0, 0.03 * Math.sin(T * 0.12), FOV);
      glints(T, (i, p) => { const a = hash(i, 2) * TAU; return [Math.cos(a) * 15, (p ? (p - 64) * 0.4 : 0) + (hash(i, 4) - 0.5) * 6, Math.sin(a) * 15]; });
    },
  },
  // crystals on slow orbits around a light; big hits send slow rings out
  swarm: {
    build() {
      O.shell = makeStarShell(800, 110, 300, D.seed + 5);
      O.swarm = makeCrystalSwarm(30, [10, 26], D.seed, [BASE, ACC, WARM_WHITE]);
      O.flare = makeFlare(26, {streak: 0.9, rays: 0.4});
      O.shocks = makeShockRings(3);
    },
    update(T, u, e) {
      updateCrystalSwarm(O.swarm, T, Math.min(1, e.pulse), e.band, 0.55 + 0.2 * e.glow);
      setFlare(O.flare, mixColor(BASE, WARM_WHITE, 0.4), 0.35 + 0.45 * e.pulse + 0.15 * e.glow, T * 0.08, 1);
      if (R.ring) updateShockRings(O.shocks, R.ring, T, ACC, {r0: 6, r1: 70, life: 4, gain: 2, face: true});
      const [x, y, z] = orbit(T, {radius: 56 - 6 * u, height: 8 - 4 * u, speed: 0.08 * DIR, phase: D.seed, bob: 3});
      aimCamera(x, y, z, 0, LOOKY * 2, 0, 0.04 * Math.sin(T * 0.1), FOV);
    },
  },
  // great rings with scale marks, the spectrum as rays around a light: the climax
  rings: {
    build() {
      O.shell = makeStarShell(800, 200, 400, D.seed + 6);
      O.rings = makeRingStructure({radii: [22, 38, 58, 80]});
      O.centre = new THREE.Group(); scene.add(O.centre);
      O.rays = makeSpectrumRays(O.centre);
      O.flare = makeFlare(30, {streak: 1, rays: 0.5});
      O.shocks = makeShockRings(3);
    },
    update(T, u, e) {
      updateRingStructure(O.rings, T, (k) => (k % 2 ? ACC : BASE), (k) => (0.5 + 0.12 * k) * (1 + 1.0 * e.pulse), 1.4);
      O.centre.quaternion.copy(camera.quaternion);
      updateSpectrumRays(O.rays, e.band, 9, 13, BASE, mixColor(ACC, WARM_WHITE, 0.2), 0.28 + 0.3 * e.glow);
      setFlare(O.flare, mixColor(BASE, WARM_WHITE, 0.45), 0.35 + 0.5 * e.pulse + 0.15 * e.glow, T * 0.06, 1);
      if (R.ring) updateShockRings(O.shocks, R.ring, T, ACC, {r0: 8, r1: 80, life: 4.5, gain: 2, face: true});
      const [x, y, z] = orbit(T, {radius: 150 - 25 * u, height: 22 - 10 * u, speed: 0.05 * DIR, phase: D.seed * 0.1, bob: 4});
      aimCamera(x, y, z, 0, LOOKY * 4, 0, 0.06 * Math.sin(T * 0.09), FOV);
    },
  },
  // a tunnel of polygons flying past, one on every beat, towards a light
  tunnel: {
    build() {
      O.stars = makeStarField(500, [18, 140], 320, D.seed + 7);
      O.tun = new Glow(8 * 26, {px: 2.0, world: 0.09, halo: 1.6, haloGain: 0.4});
      O.flare = makeFlare(60, {streak: 0.8, rays: 0.4}); O.flare.position.set(0, 0, -240);
    },
    update(T, u, e) {
      const v = D.speed ?? 11;
      aimCamera(0, 0, 0, 6 * Math.sin(T * 0.07), LOOKY + 4 * Math.sin(T * 0.05), -100, 0.18 * Math.sin(T * 0.09 + D.seed), FOV);
      updateStarField(O.stars, T, v * T, 2.2, 0, 0.8, 16);
      updateTunnel(O.tun, T, song.beat, (tk) => -(tk - T) * v - 20, 260, 15, (idx, tk) => [idx % 2 ? ACC : BASE, 1.1 * (1 + 1.2 * e.pulse), idx % 4 === 0 ? 8 : 6]);
      setFlare(O.flare, mixColor(ACC, WARM_WHITE, 0.4), 0.8 + 0.8 * e.pulse + 0.3 * e.glow, T * 0.05, 1);
    },
  },
  // the melody drawn as a ribbon of light, the camera drawing back
  ribbon: {
    build() {
      O.shell = makeStarShell(900, 100, 280, D.seed + 8);
      O.rib = makeRibbon(180, {world: 0.36, px: 2.4});
      O.flare = makeFlare(30, {streak: 0.6, rays: 0.3}); O.flare.position.set(0, 0, -60);
    },
    update(T, u, e) {
      const notes = song.notes[D.melody];
      updateRibbon(O.rib, notes, T, 9, (time, pitch, age, out) => {
        out[0] = 7 - age * (D.ribbonSpeed ?? 2.6); out[1] = (pitch ? (pitch - (D.mid ?? 70)) : 0) * 0.65 + 1.6 * Math.sin(time * 0.6); out[2] = -age * 1.2;
      }, mixColor(ACC, WARM_WHITE, 0.3), BASE, D.ribbonGain ?? 3.6, 3.4, 0.38);
      setFlare(O.flare, mixColor(BASE, WARM_WHITE, 0.3), 0.5 + 0.5 * e.glow + 0.5 * e.pulse, T * 0.03, 1);
      aimCamera(4 * Math.sin(T * 0.05), 2, 36 + 10 * u, 0, LOOKY * 0.8, -6, 0.03 * Math.sin(T * 0.1), FOV);
    },
  },
};

let gl0 = null;
function glints(T, place) {
  if (!gl0) return;
  R.glints.forEach((notes, k) => updateGlints(gl0[k], notes, T, {c: mixColor(ACC, WARM_WHITE, 0.5), life: 3.5, size: 1.2, gain: 4, place: (i, p) => place(i + 97 * k, p)}));
}

function update(t) {
  const T = M.time(t), u = smootherstep(clamp(t / Math.max(0.001, D.dur ?? 3)));
  const e = {pulse: R.pulse(T), glow: Math.min(1.4, R.glow(T)), band: (b) => M.band(b, T)};
  sky.turn(T, 0.7); sky.follow(camera);
  sky.colors(DEEP, BASE.clone().multiplyScalar(0.12), BASE.clone().multiplyScalar(0.34), (D.sky ?? 0.45) + 0.12 * e.glow);   // the sky never pulses
  sky.light(1, new THREE.Vector3(0.3, 0.5, -1), ACC, 0.22, 7);
  SETS[D.mode].update(T, u, e);
}

function addText(parent, text, css) { const d = document.createElement("div"); d.textContent = text; d.style.cssText = css; parent.append(d); return d; }

export async function load(ctx) {
  M = ctx.music; D = ctx.data;
  D.dur = ctx.duration;
  R = reactions(M, D.react ?? {}, {decay: D.decay ?? 0.2});
  song = trackArrays(M, {hits: [], notes: D.melody ? [D.melody] : []});
  song.beat = M.score.beat;
  BASE = color(D.colours.base); ACC = color(D.colours.accent); DEEP = color(D.colours.deep);
  DIR = D.seed % 2 ? 1 : -1;
  FOV = D.fov ?? (ctx.height > ctx.width ? 68 : 50);
  LOOKY = D.lookY ?? 0;
  document.documentElement.style.background = "#000"; document.body.style.background = "#000";
  const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false, stencil: true});
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
  camera = new THREE.PerspectiveCamera(FOV, ctx.width / ctx.height, 0.1, 5000);
  setStage({renderer, scene, camera, width: ctx.width, height: ctx.height});
  sky = new SkyDome(D.seed);
  SETS[D.mode].build();
  gl0 = R.glints.map(() => new Glow(60, {px: 1.5, halo: 1.6, haloGain: 0.5}));
  const fadeOut = D.fadeOut ?? 0, dur = ctx.duration;
  finish = new Finish(renderer, scene, camera, ctx, {update, toneMapping: "aces", grade: D.grade ?? {}, vignette: 0.35, grain: D.grain ?? 0.012,
    bloom: {strength: D.bloom ?? 0.55, radius: 0.4, threshold: 0.9, scale: 0.5},
    fade: (t) => (fadeOut > 0 ? clamp((dur - t) / fadeOut) : 1)});
  finish.warmUp(0);

  // the opening title (with "made with" and the link on two lines under it) or the end card
  if (D.title) {
    card = await titleCard(ctx, {title: D.title.title, subtitle: D.title.subtitle ?? "", side: "bottom", align: "left", y: D.title.y ?? 0.66,
      start: D.title.start ?? 0.15, fadeIn: D.title.fadeIn ?? 0.5, hold: D.title.hold ?? 3.2, fadeOut: D.title.fadeOut ?? 0.8, shade: 0.55, size: D.title.size ?? 4.2});
    if (D.title.made) {
      const k = ctx.width * 0.017, blk = card.element.querySelector(".vg-card-block");
      addText(blk, "made with", `margin-top:${1.2 * k}px;font:600 ${1.25 * k}px/1.2 var(--vidgen-font-body, sans-serif);letter-spacing:0.22em;color:#e9e2d4;text-transform:uppercase;white-space:nowrap;`);
      addText(blk, URL, `margin-top:${0.35 * k}px;font:600 ${1.3 * k}px/1.2 var(--vidgen-font-mono, monospace);letter-spacing:0;color:#fff3df;white-space:nowrap;text-shadow:0 0 ${0.6 * k}px rgba(120,180,255,.6);`);
    }
  } else if (D.end) {
    card = await endCard(ctx, {title: D.end.title, subtitle: D.end.subtitle ?? "", side: "bottom", align: "left", y: D.end.y ?? 0.66,
      start: D.end.start ?? 0.3, fadeIn: D.end.fadeIn ?? 1.0, shade: 0.6, size: D.end.size ?? 3.4,
      link: URL, lines: ["is open source.", "Give it a star on GitHub.", "Thank you for watching!"], lineSize: 1.95, linkSize: 1.35, lineColor: "#efe4d0"});
  }
  // an instrument label (the listening test only)
  if (D.label) {
    label = document.createElement("div"); label.dataset.vidgenId = "label";
    const k = ctx.width * 0.017;
    label.style.cssText = `position:absolute;left:0;right:0;top:${0.12 * ctx.height}px;text-align:center;pointer-events:none;color:#f3ede2;` +
      `font:600 ${2.3 * k}px/1.25 var(--vidgen-font-heading, Georgia, serif);letter-spacing:0.12em;text-transform:uppercase;text-shadow:0 0 ${0.8 * k}px rgba(0,0,0,.9),0 0 ${1.6 * k}px rgba(120,170,255,.45);`;
    label.innerHTML = "";
    addText(label, D.label[0], "");
    D.label.slice(1).forEach((l, i) => addText(label, l, `font-size:${1.45 * k}px;letter-spacing:0.12em;margin-top:${(i ? 0.25 : 0.6) * k}px;color:#c9d2e6;font-family:var(--vidgen-font-body, sans-serif);white-space:nowrap;`));
    label.style.padding = `0 ${0.06 * ctx.width}px`;
    const shade = document.createElement("div"); shade.dataset.vidgenLint = "off";
    shade.style.cssText = `position:absolute;left:0;right:0;top:0;height:${0.3 * ctx.height}px;pointer-events:none;background:linear-gradient(180deg, rgba(0,0,0,.62), rgba(0,0,0,.35) 55%, rgba(0,0,0,0));`;
    document.body.append(shade, label); label._shade = shade;
  }
}

export function frame(t, ctx) {
  finish.render(t);
  if (card) card.update(t);
  if (label) { const o = String(smoothstep(0, 0.35, t) * (D.labelFade ? smoothstep(ctx.duration, ctx.duration - 0.4, t) : 1)); label.style.opacity = o; label._shade.style.opacity = o; }
}
