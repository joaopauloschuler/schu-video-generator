// A starter page written by `vidgen music plan` (look "ribbon": the melody as a ribbon of light, the
// camera drawing back). Its scene's plan is in ctx.data: role, colours and the colour script (script),
// the tracks it follows (react: pulse, ring, glint, glow; the first glint track draws the ribbon), its
// bars in song time (start, end; until with the tail, over which the picture fades out), drops, grade,
// seed. Change anything. Everything is set from song time T and nothing is kept between frames; hits
// change light, never the camera or a size.
import * as THREE from "three";
import {reactions, colourScript, pathPoint, smootherstep, smoothstep} from "vidgen/music-time";
import {setStage, color, SkyDome, makeRibbon, updateRibbon, makeStarShell, makeFlare, setFlare, aimCamera, WARM_WHITE} from "vidgen/three-kit";
import {Finish} from "vidgen/three-finish";

const BACK = [[0, 0.5, 9], [2, 1.5, 14], [1, 3, 22], [-1, 4, 32]];   // the camera drawing back over the scene
let M, D, R, palette, finish, camera, sky, ribbon, shell, flare;

function update(t) {
  const T = M.time(t), P = palette(T), u = smootherstep((T - D.start) / (D.until - D.start));
  const pulse = R.pulse(T), glow = Math.min(1.5, R.glow(T));
  aimCamera(...pathPoint(BACK, u), 0, 0.5, 0, 0, 48);
  sky.turn(T, 0.5); sky.follow(camera);
  sky.colors(color(P.deep), color(P.base, 0.1), color(P.base, 0.3), 0.25 + 0.35 * glow);
  updateRibbon(ribbon, R.glints[0] ?? null, T, 6, (x, pitch, age, out) => {
    out[0] = 5 - age * 2.2; out[1] = (pitch - 66) * 0.18 + 0.5 * Math.sin(x * 0.9); out[2] = -age * 0.6; }, color(P.accent), color(P.base), 2.5 + 1.5 * glow);
  shell.tint(color(0xffffff), 0.5 + 0.4 * glow);
  setFlare(flare, color(P.accent), 0.3 + 1.4 * pulse, T * 0.04, 1);
}

export function load(ctx) {
  M = ctx.music; D = ctx.data;
  R = reactions(M, D.react, {drops: D.drops});
  palette = colourScript(D.script);
  const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  const scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(48, ctx.width / ctx.height, 0.1, 4000);
  setStage({renderer, scene, camera, width: ctx.width, height: ctx.height});
  sky = new SkyDome(D.seed);
  ribbon = makeRibbon(160, {px: 2.2, world: 0.12});
  shell = makeStarShell(600, 60, 220, D.seed + 1);
  flare = makeFlare(24, {streak: 0.5, rays: 0.2}); flare.position.set(5, 0, 0);
  finish = new Finish(renderer, scene, camera, ctx, {update, toneMapping: "aces", grade: D.grade, vignette: 0.4, grain: 0.02,
    bloom: {strength: 0.5, radius: 0.35, threshold: 1.0, scale: 0.5},
    flash: (t) => ({amount: 0.3 * R.drop(M.time(t)), color: 1}),
    fade: (t) => 1 - smoothstep(D.until - 2.5, D.until, M.time(t))});
  finish.warmUp(0);
}

export function frame(t) {
  finish.render(t);
}
