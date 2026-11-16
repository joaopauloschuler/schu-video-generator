// A starter page written by `vidgen music plan` (look "orbit": a tesseract the camera circles, in a
// shell of stars). Its scene's plan is in ctx.data: role, colours and the colour script (script), the
// tracks it follows (react: pulse, ring, glint, glow), its bars in song time (start, end; until with the
// tail), drops, grade, seed. Change anything. Everything is set from song time T and nothing is kept
// between frames, so the cut into the next scene does not show; hits change light, never the camera or a size.
import * as THREE from "three";
import {reactions, colourScript, orbit, smootherstep, hash} from "vidgen/music-time";
import {setStage, color, SkyDome, makeTesseract, updateTesseract, tesseractAngles, makeStarShell, makeShockRings, updateShockRings,
        Glow, updateGlints, aimCamera} from "vidgen/three-kit";
import {Finish} from "vidgen/three-finish";

let M, D, R, palette, finish, camera, sky, tes, shell, shocks, glints;

function update(t) {
  const T = M.time(t), P = palette(T), u = smootherstep((T - D.start) / (D.end - D.start));
  const pulse = R.pulse(T), glow = Math.min(1.5, R.glow(T));
  aimCamera(...orbit(T, {radius: 15 - 3 * u, height: 1.5 + 2.5 * u, speed: D.seed % 2 ? 0.09 : -0.09, phase: D.seed, bob: 0.6}), 0, 50);
  sky.turn(T); sky.follow(camera);
  sky.colors(color(P.deep), color(P.base, 0.12), color(P.base, 0.4), 0.3 + 0.35 * glow);
  updateTesseract(tes, tesseractAngles(T * 0.5), color(P.base), 1.1 + 2.2 * pulse, 1.5 + 3 * pulse);
  shell.tint(color(0xffffff), 0.6 + 0.5 * glow);
  updateShockRings(shocks, R.ring, T, color(P.accent), {r0: 2.5, r1: 22, life: 2.2, gain: 2.5, face: true});
  R.glints.forEach((notes, k) => updateGlints(glints[k], notes, T, {c: color(P.accent), life: 3, size: 0.9,
    place: (i, p) => { const a = hash(i, k + 2) * Math.PI * 2, r = 5 + 3 * hash(i, k + 5); return [Math.cos(a) * r, (p ? p - 66 : 0) * 0.15, Math.sin(a) * r]; }}));
}

export function load(ctx) {
  M = ctx.music; D = ctx.data;
  R = reactions(M, D.react, {drops: D.drops});
  palette = colourScript(D.script);
  const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  const scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(50, ctx.width / ctx.height, 0.1, 4000);
  setStage({renderer, scene, camera, width: ctx.width, height: ctx.height});
  sky = new SkyDome(D.seed);
  tes = makeTesseract({world: 0.04}); tes.scale.setScalar(2.2);
  shell = makeStarShell(700, 60, 200, D.seed + 1);
  shocks = makeShockRings(4);
  glints = R.glints.map(() => new Glow(60, {px: 1.5, halo: 1.6, haloGain: 0.5}));
  finish = new Finish(renderer, scene, camera, ctx, {update, toneMapping: "aces", grade: D.grade, vignette: 0.35, grain: 0.02,
    bloom: {strength: 0.5, radius: 0.35, threshold: 1.0, scale: 0.5},
    flash: (t) => ({amount: 0.35 * R.drop(M.time(t)), color: 1})});
  finish.warmUp(0);
}

export function frame(t) {
  finish.render(t);
}
