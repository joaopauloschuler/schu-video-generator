// A starter page written by `vidgen music plan` (look "tunnel": a flight down a tunnel of rings on the
// beat, faster as it builds). Its scene's plan is in ctx.data: role, colours and the colour script
// (script), the tracks it follows (react: pulse, ring, glint, glow), its bars in song time (start, end;
// until with the tail), drops, grade, seed, bar (seconds). Change anything. Everything is set from song
// time T and nothing is kept between frames; hits change light, never the camera or a size.
import * as THREE from "three";
import {reactions, colourScript, smoothstep, hash} from "vidgen/music-time";
import {setStage, color, SkyDome, Glow, updateTunnel, makeStarField, updateStarField, updateGlints, aimCamera, WARM_WHITE} from "vidgen/three-kit";
import {Finish} from "vidgen/three-finish";

const RINGS = 28, FAR = 140;
let M, D, R, palette, finish, camera, sky, tunnel, stars, glints;
// how far the flight has gone at song time x: 10 units a second, up to 26 by the scene's end
const flown = (x) => { const a = Math.max(0, x - D.start), len = D.end - D.start; return 10 * x + 8 * a * a / len; };

function update(t) {
  const T = M.time(t), P = palette(T), build = smoothstep(D.start, D.end, T);
  const pulse = R.pulse(T), glow = Math.min(1.5, R.glow(T)), here = flown(T);
  aimCamera(0.6 * Math.sin(T * 0.3), 0.4 * Math.cos(T * 0.23), 0, 0, 0, -40, 0.15 * Math.sin(T * 0.11) + 0.2 * build, 60 + 8 * build);
  sky.turn(T, 2); sky.follow(camera);
  sky.colors(color(P.deep), color(P.base, 0.1), color(P.base, 0.3), 0.25 + 0.3 * glow);
  const base = color(P.base), accent = color(P.accent);
  updateTunnel(tunnel, T, D.bar / 4, (x) => here - flown(x), FAR, 7,
    (i) => [i % 4 === 0 ? accent : base, (0.8 + 0.8 * build) * (1 + 1.8 * pulse), i % 4 === 0 ? 3 : 6]);
  updateStarField(stars, T, here, 2 + 10 * build, 0, 0.7 + 0.5 * glow);
  R.glints.forEach((notes, k) => updateGlints(glints[k], notes, T, {c: WARM_WHITE, life: 2.5, size: 0.7,
    place: (i, p) => { const a = hash(i, k + 4) * Math.PI * 2; return [Math.cos(a) * 4.5, Math.sin(a) * 4.5 + (p ? p - 66 : 0) * 0.02, -18 - 8 * hash(i, k + 9)]; }}));
}

export function load(ctx) {
  M = ctx.music; D = ctx.data;
  R = reactions(M, D.react, {drops: D.drops});
  palette = colourScript(D.script);
  const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  const scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(60, ctx.width / ctx.height, 0.1, 4000);
  setStage({renderer, scene, camera, width: ctx.width, height: ctx.height});
  sky = new SkyDome(D.seed);
  tunnel = new Glow(RINGS * 8, {px: 1.6, world: 0.06, halo: 1.6, haloGain: 0.4, fog: [60, FAR]});
  stars = makeStarField(400, [9, 60], 260, D.seed + 1);
  glints = R.glints.map(() => new Glow(60, {px: 1.5, halo: 1.6, haloGain: 0.5}));
  finish = new Finish(renderer, scene, camera, ctx, {update, toneMapping: "aces", grade: D.grade, vignette: 0.4, grain: 0.02,
    bloom: {strength: 0.5, radius: 0.35, threshold: 1.0, scale: 0.5},
    flash: (t) => ({amount: 0.35 * R.drop(M.time(t)), color: 1})});
  finish.warmUp(0);
}

export function frame(t) {
  finish.render(t);
}
