// A small still life in metal, finished with vidgen's "vidgen/three-finish" (`vidgen guide web`,
// "Finishing three.js scenes"): brass gears and a row of spheres on slate, lit by a baked studio of
// soft boxes, one shadowed key light, the focus pulled from the front sphere to the gear at the back,
// a fast gear blurred by motion blur, bloom on the highlights, ACES, a grade, vignette and grain.
//
// update(t) sets the whole scene to time t and keeps no state, so motion blur can call it at
// sub-frame times. ctx.data.off lists effects to leave out (bloom, dof, motion, grade, vignette,
// grain, fxaa, tone), ctx.data.finish overrides options: both only for comparing stills.
import * as THREE from "three";
import {Finish, focusDistance, studioEnvironment, surfaceFinish, softShadows} from "vidgen/three-finish";

let finish, camera, spinner, gears = [], spheres = [];
const ease = (u) => { u = Math.min(1, Math.max(0, u)); return u * u * (3 - 2 * u); };

function gearGeometry(teeth, radius, depth, hole) {
  const shape = new THREE.Shape(), pitch = (Math.PI * 2) / teeth, inner = radius * 0.9;
  for (let i = 0; i < teeth; i++) {
    const a = i * pitch;
    const pts = [[inner, a], [radius, a + pitch * 0.18], [radius, a + pitch * 0.48], [inner, a + pitch * 0.66]];
    pts.forEach(([r, b], k) => (i === 0 && k === 0 ? shape.moveTo : shape.lineTo).call(shape, r * Math.cos(b), r * Math.sin(b)));
  }
  shape.closePath();
  for (let k = 0; k < 5; k++) {   // five round windows between the spokes
    const a = (k / 5) * Math.PI * 2, c = radius * 0.55, w = new THREE.Path();
    w.absarc(c * Math.cos(a), c * Math.sin(a), radius * 0.2, 0, Math.PI * 2, true);
    shape.holes.push(w);
  }
  const bore = new THREE.Path(); bore.absarc(0, 0, hole, 0, Math.PI * 2, true); shape.holes.push(bore);
  const g = new THREE.ExtrudeGeometry(shape, {depth, bevelEnabled: true, bevelThickness: depth * 0.15, bevelSize: depth * 0.12, bevelSegments: 2, curveSegments: 6});
  g.translate(0, 0, -depth / 2);
  const p = g.attributes.position, uv = g.attributes.uv;   // texture coordinates about the centre, for circular graining
  for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i) / (2.2 * radius) + 0.5, p.getY(i) / (2.2 * radius) + 0.5);
  return g;
}

function update(t) {
  spinner.rotation.z = -t * 24;                // nearly 4 turns a second: a 180-degree shutter smears 0.4 rad
  gears[0].rotation.z = t * 0.35;
  gears[1].rotation.z = -t * 0.35 * (24 / 16);
  const u = ease((t - 0.5) / 5);
  camera.position.set(-2.6 + 1.2 * u, 1.35 - 0.15 * u, 4.6 - 0.5 * u);
  camera.lookAt(0.2, 0.45, 0);
}

export function load(ctx) {
  const off = new Set(ctx.data.off ?? []);
  const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x07080a);
  scene.fog = new THREE.Fog(0x07080a, 5, 11);   // the table fades into the dark
  scene.environment = studioEnvironment(renderer, {preset: "studio"});
  scene.environmentIntensity = 0.9;
  camera = new THREE.PerspectiveCamera(32, ctx.width / ctx.height, 0.1, 60);

  const brushed = surfaceFinish("brushed", {size: 256, roughness: [0.32, 0.08]});
  const circular = surfaceFinish("circular", {size: 512, roughness: [0.28, 0.06]});
  const metal = (color, roughness, finishMaps = null) => new THREE.MeshStandardMaterial({color, metalness: 1, roughness,
    ...(finishMaps ? {normalMap: finishMaps.normalMap, normalScale: new THREE.Vector2(0.5, 0.5)} : {})});
  const brass = metal(0xd9a441, 0.3, circular);

  const slate = new THREE.Mesh(new THREE.PlaneGeometry(30, 30), new THREE.MeshStandardMaterial({color: 0x1a1b1e, roughness: 0.55, metalness: 0}));
  slate.rotation.x = -Math.PI / 2; slate.receiveShadow = true; scene.add(slate);

  // two gears in mesh standing at the back, a third lying flat, the fast one in front of them
  const g1 = new THREE.Mesh(gearGeometry(24, 0.62, 0.12, 0.08), brass), g2 = new THREE.Mesh(gearGeometry(16, 0.42, 0.12, 0.06), brass);
  g1.position.set(0.9, 0.66, -1.6); g2.position.set(0.9 - 1.0, 0.46, -1.6);
  const flat = new THREE.Mesh(gearGeometry(30, 0.8, 0.1, 0.1), metal(0x9fa4aa, 0.38, circular));
  flat.material.normalScale.set(0.25, 0.25);
  flat.rotation.x = -Math.PI / 2; flat.position.set(-1.25, 0.06, -0.9);
  spinner = new THREE.Mesh(gearGeometry(12, 0.34, 0.08, 0.05), metal(0xf0c060, 0.22));
  spinner.position.set(1.55, 0.38, 0.15); spinner.rotation.y = -0.5;
  gears = [g1, g2];
  for (const m of [g1, g2, flat, spinner]) { m.castShadow = m.receiveShadow = true; scene.add(m); }

  // spheres from the front to the back: chrome, gold, brushed steel, copper, black lacquer
  const kinds = [metal(0xe8eaee, 0.05), metal(0xf2c870, 0.15), metal(0xc4c9cf, 0.3, brushed), metal(0xd08868, 0.2),
    new THREE.MeshPhysicalMaterial({color: 0x050505, roughness: 0.25, clearcoat: 1, clearcoatRoughness: 0.03})];
  kinds.forEach((material, i) => {
    const r = 0.26, s = new THREE.Mesh(new THREE.SphereGeometry(r, 48, 24), material);
    s.position.set(-0.9 + i * 0.62, r, 1.0 - i * 0.55); s.castShadow = s.receiveShadow = true;
    scene.add(s); spheres.push(s);
  });
  // a small lamp: values above 1 are what bloom picks up
  const lamp = new THREE.Mesh(new THREE.TorusGeometry(0.16, 0.025, 12, 48), new THREE.MeshBasicMaterial({color: new THREE.Color(1.0, 0.55, 0.22).multiplyScalar(6)}));
  lamp.position.set(-1.25, 0.2, -0.9); lamp.rotation.x = -Math.PI / 2; scene.add(lamp);

  const key = new THREE.DirectionalLight(0xfff1e0, 1.6);
  key.position.set(-4, 7, 4);
  softShadows(renderer, key, {type: "pcf", radius: 2, mapSize: 2048});
  Object.assign(key.shadow.camera, {left: -4, right: 4, top: 4, bottom: -4, near: 1, far: 20});
  scene.add(key);

  const front = spheres[0], back = g1;
  finish = new Finish(renderer, scene, camera, ctx, {
    update,
    bloom: !off.has("bloom"),                    // the defaults: strength 0.25, radius 0.2, threshold 1 (linear), half size
    toneMapping: off.has("tone") ? "none" : "aces",
    grade: off.has("grade") ? {} : (t) => ({temperature: 0.12 - 0.2 * ease((t - 1) / 4), saturation: 1.05, contrast: 1.04, lift: [0.004, 0.006, 0.012]}),
    vignette: off.has("vignette") ? 0 : 0.35,
    grain: off.has("grain") ? 0 : 0.02,
    antialias: off.has("fxaa") ? "none" : "fxaa",
    // the focus pull: from the front sphere to the gears at the back between 1.5 s and 4 s
    dof: off.has("dof") ? false : (t) => ({focus: THREE.MathUtils.lerp(focusDistance(camera, front), focusDistance(camera, back), ease((t - 1.5) / 2.5)),
      fStop: 2.8, unit: 0.1, maxBlur: 12, quality: "medium"}),
    motionBlur: off.has("motion") ? false : {samples: 6, shutter: 180},
    ...(ctx.data.finish ?? {}),
  });
  finish.warmUp(0);
}

export function frame(t) {
  finish.render(t);
}
