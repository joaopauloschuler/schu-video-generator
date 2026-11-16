// A starter page written by `vidgen music plan` (look "dust": one crystal in drifting dust, the camera
// close and slow). Its scene's plan is in ctx.data: role, colours and the colour script (script), the
// tracks it follows (react: pulse, ring, glint, glow), its bars in song time (start, end; until with the
// tail), drops, grade, seed. Change anything. Everything is set from song time T and nothing is kept
// between frames; hits change light, never the camera or a size.
import * as THREE from "three";
import {reactions, colourScript, orbit, smootherstep, hash} from "vidgen/music-time";
import {setStage, color, SkyDome, makeCrystal, lightCrystal, makeDustCloud, updateDustCloud, Glow, updateGlints, aimCamera, WARM_WHITE} from "vidgen/three-kit";
import {Finish} from "vidgen/three-finish";

let M, D, R, palette, finish, camera, sky, crystal, dust, glints;

function update(t) {
  const T = M.time(t), P = palette(T), u = smootherstep((T - D.start) / (D.end - D.start));
  const pulse = R.pulse(T), glow = Math.min(1.5, R.glow(T));
  aimCamera(...orbit(T, {radius: 11 - 2 * u, height: 1 + u, speed: D.seed % 2 ? 0.04 : -0.04, phase: D.seed, bob: 0.4}), 0, 45);
  sky.turn(T, 0.4); sky.follow(camera);
  sky.colors(color(P.deep), color(P.base, 0.08), color(P.base, 0.25), 0.2 + 0.3 * glow);
  crystal.rotation.set(T * 0.07, T * 0.11, 0.3);
  lightCrystal(crystal, Math.min(1, pulse), 0.6 + 0.5 * glow);
  updateDustCloud(dust, T, color(P.accent), 0.35 + 0.45 * glow, 0.2);
  R.glints.forEach((notes, k) => updateGlints(glints[k], notes, T, {c: color(P.accent), life: 4, size: 0.5,
    place: (i, p) => { const a = hash(i, k + 2) * Math.PI * 2, r = 3.5 + 2 * hash(i, k + 5); return [Math.cos(a) * r, (p ? p - 66 : 0) * 0.08, Math.sin(a) * r]; }}));
}

export function load(ctx) {
  M = ctx.music; D = ctx.data;
  R = reactions(M, D.react, {drops: D.drops});
  palette = colourScript(D.script);
  const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  const scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(45, ctx.width / ctx.height, 0.1, 4000);
  setStage({renderer, scene, camera, width: ctx.width, height: ctx.height});
  sky = new SkyDome(D.seed);
  crystal = makeCrystal(["ico", "octa", "dodeca"][D.seed % 3], color(D.colours.base), color(D.colours.accent), {gain: 1.4, world: 0.03});
  crystal.scale.setScalar(2.4);
  dust = makeDustCloud(500, [30, 16, 30, 0, 0, 0], 0.12, D.seed);
  glints = R.glints.map(() => new Glow(60, {px: 1.4, halo: 1.6, haloGain: 0.5}));
  finish = new Finish(renderer, scene, camera, ctx, {update, toneMapping: "aces", grade: D.grade, vignette: 0.45, grain: 0.025,
    bloom: {strength: 0.5, radius: 0.35, threshold: 1.0, scale: 0.5},
    flash: (t) => ({amount: 0.3 * R.drop(M.time(t)), color: 1})});
  finish.warmUp(0);
}

export function frame(t) {
  finish.render(t);
}
