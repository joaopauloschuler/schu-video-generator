// A starter page written by `vidgen music plan` (look "drift": a slow flight through a nebula and
// stars). Its scene's plan is in ctx.data: role, colours and the colour script (script), the tracks it
// follows (react: pulse, ring, glint, glow), its bars in song time (start, end; until with the tail),
// drops, grade, seed. Change anything. Everything is set from song time T and nothing is kept between
// frames, so the cut into the next scene does not show; hits change light, never the camera or a size.
import * as THREE from "three";
import {reactions, colourScript, flyThrough, smootherstep, hash} from "vidgen/music-time";
import {setStage, color, SkyDome, makeStarField, updateStarField, makeFlare, setFlare, Glow, updateGlints, aimCamera} from "vidgen/three-kit";
import {Finish} from "vidgen/three-finish";

const PATH = [[0, 0.5, 12], [1.5, 1.2, 6], [-1, 0.6, 0], [0.5, 0, -6]];   // the flight over the scene's bars
let M, D, R, palette, finish, camera, sky, stars, flare, glints;

function update(t) {
  const T = M.time(t), P = palette(T), u = smootherstep((T - D.start) / (D.end - D.start));
  const pulse = R.pulse(T), glow = Math.min(1.5, R.glow(T));
  aimCamera(...flyThrough(PATH, u, 0.25), 0.04 * Math.sin(T * 0.2), 55);
  sky.turn(T, 0.6); sky.follow(camera);
  sky.colors(color(P.deep), color(P.base, 0.18), color(P.base, 0.55), 0.45 + 0.4 * glow);
  sky.light(1, new THREE.Vector3(0.2, 0.1, -1), color(P.accent), 0.25 + 0.6 * pulse, 8);
  updateStarField(stars, T, 3 * T, 0, camera.position.z, 0.8 + 0.4 * glow);
  setFlare(flare, color(P.accent), 0.4 + 1.6 * pulse + 0.5 * glow, T * 0.05, 1);
  R.glints.forEach((notes, k) => updateGlints(glints[k], notes, T, {c: color(P.accent), life: 4, size: 1.2,
    place: (i, p) => [(hash(i, k + 1) - 0.5) * 16, (p ? p - 66 : 0) * 0.2 + (hash(i, k + 7) - 0.5) * 4, -12 - 12 * hash(i, k + 3)]}));
}

export function load(ctx) {
  M = ctx.music; D = ctx.data;
  R = reactions(M, D.react, {drops: D.drops});
  palette = colourScript(D.script);
  const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  const scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(55, ctx.width / ctx.height, 0.1, 4000);
  setStage({renderer, scene, camera, width: ctx.width, height: ctx.height});
  sky = new SkyDome(D.seed);
  stars = makeStarField(500, [6, 120], 300, D.seed + 1);
  flare = makeFlare(40, {streak: 0.6, rays: 0.3}); flare.position.set(0, 2, -90);
  glints = R.glints.map(() => new Glow(60, {px: 1.5, halo: 1.6, haloGain: 0.5}));
  finish = new Finish(renderer, scene, camera, ctx, {update, toneMapping: "aces", grade: D.grade, vignette: 0.4, grain: 0.02,
    bloom: {strength: 0.5, radius: 0.35, threshold: 1.0, scale: 0.5},
    flash: (t) => ({amount: 0.35 * R.drop(M.time(t)), color: 1})});
  finish.warmUp(0);
}

export function frame(t) {
  finish.render(t);
}
