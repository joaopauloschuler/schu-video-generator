// A starter page written by `vidgen music plan` (look "swarm": a swarm of crystals around a flare,
// rings from the accents). Its scene's plan is in ctx.data: role, colours and the colour script
// (script), the tracks it follows (react: pulse, ring, glint, glow), its bars in song time (start, end;
// until with the tail), drops, grade, seed. Change anything. Everything is set from song time T and
// nothing is kept between frames; hits change light, never the camera or a size.
import * as THREE from "three";
import {reactions, colourScript, orbit, smootherstep, hash} from "vidgen/music-time";
import {setStage, color, SkyDome, makeCrystalSwarm, updateCrystalSwarm, makeFlare, setFlare, makeShockRings, updateShockRings,
        Glow, updateGlints, aimCamera, WARM_WHITE} from "vidgen/three-kit";
import {Finish} from "vidgen/three-finish";

let M, D, R, palette, finish, camera, sky, swarm, flare, shocks, glints;

function update(t) {
  const T = M.time(t), P = palette(T), u = smootherstep((T - D.start) / (D.end - D.start));
  const pulse = R.pulse(T), glow = Math.min(1.5, R.glow(T)), band = (b) => M.band(b, T);
  aimCamera(...orbit(T, {radius: 40 - 8 * u, height: 6 - 4 * u, speed: D.seed % 2 ? 0.12 : -0.12, phase: D.seed, bob: 2}), 0.05 * Math.sin(T * 0.3), 52);
  sky.turn(T, 1.5); sky.follow(camera);
  sky.colors(color(P.deep), color(P.base, 0.12), color(P.base, 0.35), 0.3 + 0.35 * glow);
  updateCrystalSwarm(swarm, T, pulse, band, 0.7 + 0.4 * glow);
  setFlare(flare, color(P.base), 1.0 + 2.5 * pulse + 0.8 * glow, T * 0.1, 1);
  updateShockRings(shocks, R.ring, T, color(P.accent), {r0: 3, r1: 40, life: 2.5, gain: 3, face: true});
  R.glints.forEach((notes, k) => updateGlints(glints[k], notes, T, {c: WARM_WHITE, life: 3, size: 1.4,
    place: (i, p) => { const a = hash(i, k + 2) * Math.PI * 2, r = 12 + 10 * hash(i, k + 5); return [Math.cos(a) * r, (p ? p - 66 : 0) * 0.3, Math.sin(a) * r]; }}));
}

export function load(ctx) {
  M = ctx.music; D = ctx.data;
  R = reactions(M, D.react, {drops: D.drops});
  palette = colourScript(D.script);
  const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  const scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(52, ctx.width / ctx.height, 0.1, 4000);
  setStage({renderer, scene, camera, width: ctx.width, height: ctx.height});
  sky = new SkyDome(D.seed);
  swarm = makeCrystalSwarm(26, [7, 28], D.seed, [color(D.colours.base), color(D.colours.accent), WARM_WHITE]);
  flare = makeFlare(30, {streak: 0.9, rays: 0.4});
  shocks = makeShockRings(5);
  glints = R.glints.map(() => new Glow(60, {px: 1.5, halo: 1.6, haloGain: 0.5}));
  finish = new Finish(renderer, scene, camera, ctx, {update, toneMapping: "aces", grade: D.grade, vignette: 0.35, grain: 0.02,
    bloom: {strength: 0.5, radius: 0.35, threshold: 1.0, scale: 0.5},
    flash: (t) => ({amount: 0.4 * R.drop(M.time(t)), color: 1})});
  finish.warmUp(0);
}

export function frame(t) {
  finish.render(t);
}
