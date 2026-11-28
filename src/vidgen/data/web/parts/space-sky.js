// The ready-made skies of vidgen/space-sky for the registry vidgen/parts:
// what `vidgen parts` draws on its contact sheet. The skies are drawn straight to the canvas
// ({finish: false}: the sky applies the tone curve itself, and three-finish's FXAA would smear the
// stars of a small tile); the particle galaxy, whose sprites add up in linear light, goes through
// vidgen/three-finish.
import * as THREE from "three";
import {definePart} from "vidgen/parts";
import {spaceSky, spiralGalaxy} from "vidgen/space-sky";

// a small tile gets a small cube map: the picture is the same, the bake four times quicker
const size = (s) => (s.height >= 150 ? null : 256);
function look(s, sky, to, {fov = 50, up = null} = {}) {
  const d = sky.direction(to);
  s.camera.position.set(0, 0, 0); s.camera.up.copy(up ? sky.direction(up) : new THREE.Vector3(0, 1, 0));
  s.camera.fov = fov; s.camera.lookAt(d); s.camera.updateProjectionMatrix(); s.camera.updateMatrixWorld();
}
function show(s, options, to, view) {
  const sky = spaceSky(s.renderer, {size: size(s), ...options});
  s.scene.add(sky.object);
  look(s, sky, to, view);
  return sky;
}

definePart({"name": "space-sky", "kind": "sky", "module": "vidgen/space-sky",
  "label": "a sky from a seed: stars by magnitude and colour, the Milky Way with its dust",
  "use": "const sky = spaceSky(renderer, {seed}); scene.add(sky.object)",
  "options": {"l": 35, "b": 12, "fov": 75}, "seed": 1},
(s) => { show(s, {seed: s.seed}, {l: s.options.l, b: s.options.b}, {fov: s.options.fov, up: "pole"}); return {finish: false}; });

definePart({"name": "space-sky-core", "kind": "sky", "module": "vidgen/space-sky",
  "label": "the Milky Way's core: the warm bulge, the dark rift, star clouds",
  "use": "const sky = spaceSky(renderer, {seed}); camera.lookAt(sky.direction(\"center\"))",
  "options": {"fov": 40}, "seed": 1},
(s) => { show(s, {seed: s.seed}, "center", {fov: s.options.fov, up: "pole"}); return {finish: false}; });

definePart({"name": "space-sky-rich", "kind": "sky", "module": "vidgen/space-sky",
  "label": "a rich sky: more stars, a brighter band, a few nebulae and galaxies",
  "use": "spaceSky(renderer, {seed, look: \"rich\"})",
  "options": {"l": 25, "b": 4, "fov": 60}, "seed": 3},
(s) => { show(s, {seed: s.seed, look: "rich"}, {l: s.options.l, b: s.options.b}, {fov: s.options.fov, up: "pole"}); return {finish: false}; });

definePart({"name": "space-sky-sparse", "kind": "sky", "module": "vidgen/space-sky",
  "label": "a sparse sky far from the band: few stars, a faint band, small far galaxies",
  "use": "spaceSky(renderer, {seed, look: \"sparse\"})",
  "options": {"l": 24, "b": 16, "fov": 60}, "seed": 3},
(s) => { show(s, {seed: s.seed, look: "sparse"}, {l: s.options.l, b: s.options.b}, {fov: s.options.fov, up: "pole"}); return {finish: false}; });

definePart({"name": "space-sky-emission-nebula", "kind": "sky", "module": "vidgen/space-sky",
  "label": "an emission nebula on the band: red hydrogen, pink where dense, dark lanes",
  "use": "spaceSky(renderer, {seed, nebulae: [{kind: \"emission\", at: {l: 20, b: 3}, size: 7}]})",
  "options": {"l": 20, "b": 3, "size": 7, "fov": 28}, "seed": 1},
(s) => {
  const o = s.options;
  show(s, {seed: s.seed, nebulae: [{kind: "emission", at: {l: o.l, b: o.b}, size: o.size, seed: 421, angle: 30, stretch: 1.3}]}, "nebula 1", {fov: o.fov, up: "pole"});
  return {finish: false};
});

definePart({"name": "space-sky-reflection-nebula", "kind": "sky", "module": "vidgen/space-sky",
  "label": "a reflection nebula: blue dust lit by its stars, off the band",
  "use": "spaceSky(renderer, {seed, nebulae: [{kind: \"reflection\", at: {l: 150, b: -18}, size: 5}]})",
  "options": {"l": 150, "b": -18, "size": 5, "fov": 24}, "seed": 2},
(s) => {
  const o = s.options;
  show(s, {seed: s.seed, nebulae: [{kind: "reflection", at: {l: o.l, b: o.b}, size: o.size, seed: 77, strength: 1.6}]}, "nebula 1", {fov: o.fov});
  return {finish: false};
});

definePart({"name": "space-sky-dark-nebula", "kind": "sky", "module": "vidgen/space-sky",
  "label": "a dark nebula: a cloud that hides the band behind it",
  "use": "spaceSky(renderer, {seed, nebulae: [{kind: \"dark\", at: {l: -14, b: -5}, size: 7}]})",
  "options": {"l": -14, "b": -5, "size": 7, "fov": 36}, "seed": 1},
(s) => {
  const o = s.options;
  show(s, {seed: s.seed, nebulae: [{kind: "dark", at: {l: o.l, b: o.b}, size: o.size, seed: 5, stretch: 1.6}]}, "nebula 1", {fov: o.fov, up: "pole"});
  return {finish: false};
});

definePart({"name": "space-sky-galaxies", "kind": "sky", "module": "vidgen/space-sky",
  "label": "far galaxies painted into the sky: spiral, edge-on, elliptical, irregular",
  "use": "spaceSky(renderer, {seed, galaxies: [{kind: \"spiral\", at: {l: 100, b: 55}, size: 6, tilt: 55}]})",
  "options": {"fov": 18}, "seed": 1},
(s) => {
  const galaxies = [{at: {l: 100, b: 55}, size: 6, tilt: 55, angle: 150, seed: 398, arms: 2, strength: 1.3}, {kind: "elliptical", at: {l: 112, b: 60}, size: 1.5, seed: 4},
    {at: {l: 92, b: 62}, size: 2, tilt: 80, angle: 100, seed: 9}, {kind: "irregular", at: {l: 108, b: 48}, size: 3, seed: 6}];
  show(s, {seed: s.seed, galaxies}, {l: 103, b: 55}, {fov: s.options.fov, up: "pole"});
  return {finish: false};
});

definePart({"name": "space-sky-real", "kind": "sky", "module": "vidgen/space-sky",
  "label": "the real sky (here: toward Orion): true bright stars, the band where it is",
  "use": "const sky = spaceSky(renderer, {stars: \"real\"}); camera.lookAt(sky.direction(\"Alnilam\"))",
  "options": {"toward": "Alnilam", "fov": 32}},
(s) => {
  const sky = show(s, {stars: "real"}, s.options.toward, {fov: s.options.fov});
  s.camera.up.set(0, 0.9175, -0.3978); s.camera.lookAt(sky.direction(s.options.toward)); s.camera.updateMatrixWorld();   // celestial north up
  return {finish: false};
});

definePart({"name": "spiral-galaxy", "kind": "sky", "module": "vidgen/space-sky",
  "label": "a spiral galaxy of particles to fly past: glowing arms, dust, a warm bulge",
  "use": "const g = spiralGalaxy({seed, radius}); scene.add(g.object)",
  "options": {"radius": 1, "arms": 2, "tilt": 55, "distance": 2.6}, "seed": 1},
(s) => {
  const o = s.options, sky = show(s, {seed: 5, look: "sparse", galaxies: 0}, {l: 80, b: 50}, {fov: 40});
  const galaxy = spiralGalaxy({seed: s.seed, radius: o.radius, arms: o.arms});
  galaxy.object.position.copy(sky.direction({l: 80, b: 50})).multiplyScalar(o.distance);
  galaxy.object.rotation.set(o.tilt * Math.PI / 180, 0.4, 0.35);
  s.scene.add(galaxy.object);
  return {frame(t) { galaxy.object.rotation.y = 0.4 + t * 0.02; }};
});

definePart({"name": "space-sky-environment", "kind": "environment", "module": "vidgen/space-sky",
  "label": "the sky as an environment: metal reflects the band and the bright stars",
  "use": "scene.environment = spaceSky(renderer, {seed}).environment",
  "options": {"roughness": 0.18}, "seed": 1},
(s) => {
  const sky = show(s, {seed: s.seed}, {l: 150, b: 25}, {fov: 40, up: "pole"});
  s.scene.environment = sky.environment; s.scene.environmentIntensity = 6;
  const ball = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 48), new THREE.MeshStandardMaterial({color: 0xd8dde6, metalness: 1, roughness: s.options.roughness}));
  ball.position.copy(sky.direction({l: 150, b: 25})).multiplyScalar(5.2);
  s.scene.add(ball);
  s.key.position.copy(sky.direction("center")); s.key.intensity = 1.6;
});
