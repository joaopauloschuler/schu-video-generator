// A starter page written by `vidgen music plan` (look "rings": great rings, a crystal field and the
// spectrum as rays around a flare). Its scene's plan is in ctx.data: role, colours and the colour
// script (script), the tracks it follows (react: pulse, ring, glint, glow), its bars in song time
// (start, end; until with the tail), drops, grade, seed. Change anything. Everything is set from song
// time T and nothing is kept between frames; hits change light, never the camera or a size.
import * as THREE from "three";
import {reactions, colourScript, orbit, smootherstep} from "vidgen/music-time";
import {setStage, color, mixColor, SkyDome, makeRingStructure, updateRingStructure, makeCrystalField, updateCrystalField, makeSpectrumRays,
        updateSpectrumRays, makeFlare, setFlare, makeShockRings, updateShockRings, aimCamera, WARM_WHITE} from "vidgen/three-kit";
import {Finish} from "vidgen/three-finish";

let M, D, R, palette, finish, camera, sky, rings, field, centre, rays, flare, shocks;

function update(t) {
  const T = M.time(t), P = palette(T), u = smootherstep((T - D.start) / (D.end - D.start));
  const pulse = R.pulse(T), glow = Math.min(1.5, R.glow(T)), band = (b) => M.band(b, T);
  const base = color(P.base), accent = color(P.accent);
  aimCamera(...orbit(T, {radius: 110 - 30 * u, height: 18 - 10 * u, speed: D.seed % 2 ? 0.05 : -0.05, phase: D.seed * 0.1}), 0.1 * Math.sin(T * 0.13), 50);
  sky.turn(T, 2); sky.follow(camera);
  sky.colors(color(P.deep), color(P.base, 0.15), color(P.base, 0.25), 0.3 + 0.3 * glow);
  updateRingStructure(rings, T, (k) => k % 2 ? accent : base, (k) => (0.5 + 0.2 * k) * (1 + 1.2 * pulse), 1.5);
  updateCrystalField(field, T, 2 * T, pulse, band, 130, 0.8 + 0.4 * glow);     // crystals all about the centre, drifting
  centre.quaternion.copy(camera.quaternion);                                    // the rays face the camera
  updateSpectrumRays(rays, band, 9, 34, base, mixColor(accent, WARM_WHITE, 0.3), 0.4 + 0.6 * glow);
  setFlare(flare, mixColor(base, WARM_WHITE, 0.4), 0.6 + 1.4 * pulse + 0.4 * glow, T * 0.08, 1);
  updateShockRings(shocks, R.ring, T, accent, {r0: 8, r1: 90, life: 3, gain: 3, face: true});
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
  rings = makeRingStructure();
  field = makeCrystalField(30, [30, 90], 260, D.seed, [color(D.colours.base), color(D.colours.accent), WARM_WHITE]);
  centre = new THREE.Group(); scene.add(centre);
  rays = makeSpectrumRays(centre);
  flare = makeFlare(50, {streak: 1, rays: 0.5});
  shocks = makeShockRings(4);
  finish = new Finish(renderer, scene, camera, ctx, {update, toneMapping: "aces", grade: D.grade, vignette: 0.35, grain: 0.02,
    bloom: {strength: 0.5, radius: 0.35, threshold: 1.0, scale: 0.5},
    flash: (t) => ({amount: 0.45 * R.drop(M.time(t)), color: 1})});
  finish.warmUp(0);
}

export function frame(t) {
  finish.render(t);
}
